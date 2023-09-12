from pathlib import Path

import einops
import numpy as np
import torch

from kappadata.datasets.kd_wrapper import KDWrapper
from kappadata.utils.global_rng import GlobalRng


class KDPseudoLabelWrapper(KDWrapper):
    def __init__(
            self,
            dataset,
            uri,
            threshold=None,
            topk=None,
            tau=None,
            seed=None,
            shuffle_world_size=None,
            splits=1,
            **kwargs,
    ):
        super().__init__(dataset=dataset, **kwargs)
        assert len(self.dataset.getshape_class()) == 1

        # load pseudo labels
        if uri is not None:
            if not isinstance(uri, Path):
                uri = Path(uri)
            uri = uri.expanduser()
            assert uri.exists(), f"'{uri.as_posix()}' does not exist"
            pseudo_labels = torch.load(uri, map_location="cpu").float()
            assert len(pseudo_labels) == len(self.dataset)
            assert pseudo_labels.ndim == 1 or pseudo_labels.ndim == 2
            if pseudo_labels.ndim == 2 and pseudo_labels.size(1) == 1:
                pseudo_labels = pseudo_labels.squeeze()
            if pseudo_labels.ndim == 2:
                assert pseudo_labels.size(1) == self.dataset.getshape_class()[0]
        else:
            raise NotImplementedError

        # TODO remove
        # shuffle labels like they were generated by stacking the predictions of 4 seperate GPUs
        if shuffle_world_size is not None:
            # pad to unclipped length
            num_padded_samples = shuffle_world_size - len(pseudo_labels) % shuffle_world_size
            if num_padded_samples > 0:
                pseudo_labels = torch.concat([pseudo_labels, pseudo_labels[:num_padded_samples]])
            # revert order
            pseudo_labels = einops.rearrange(
                pseudo_labels,
                "(len_per_gpu num_gpus) ... -> (num_gpus len_per_gpu) ...",
                num_gpus=shuffle_world_size,
            )
            # clip
            if num_padded_samples > 0:
                pseudo_labels = pseudo_labels[:len(self)]


        # set properties
        self.pseudo_labels = pseudo_labels
        self.threshold = threshold
        self.topk = topk
        self.tau = tau
        self.splits = splits
        self.seed = seed

        # generate static indices for splits
        if self.splits > 1:
            if self.seed is not None:
                rng = np.random.default_rng(seed=self.seed)
            else:
                rng = self._global_rng
            self.split_indices = (rng.permutation(len(self)) % self.splits).astype(int)
        else:
            self.split_indices = None

    def getshape_class(self):
        og_shape = self.dataset.getshape_class()
        assert len(og_shape) == 1
        return self.splits * og_shape[0],

    @property
    def _global_rng(self):
        return GlobalRng()

    # noinspection PyUnusedLocal
    def getitem_class(self, idx, ctx=None):
        item = self._getitem_class(idx)
        if torch.is_tensor(item):
            item = item.long().item()
        # assign to a split
        # Example: 1000 samples with 100 classes -> with 2 splits there are 1000 samples with 200 classes evenly split
        if self.split_indices is not None:
            split_idx = self.split_indices[idx]
            item += self.dataset.getshape_class()[0] * split_idx
        return item

    def _getitem_class(self, idx):
        if self.seed is not None:
            # static pseudo labels (they dont change from epoch to epoch)
            rng = np.random.default_rng(seed=self.seed + idx)
        else:
            # dynamic pseudo labels (resampled for every epoch)
            rng = self._global_rng

        # sample pseudo labels
        if self.topk is not None:
            assert self.threshold is None, "threshold with sampled pseudo labels is not supported"
            # sample from topk
            assert self.pseudo_labels.ndim == 2
            topk_probs, topk_idxs = self.pseudo_labels[idx].topk(k=self.topk)
            if self.tau == float("inf"):
                # uniform sample
                choice = rng.integers(self.topk)
            else:
                if self.tau is not None:
                    # labels are logits -> divide by temperature and apply softmax
                    weights = topk_probs.div_(self.tau).softmax(dim=0)
                else:
                    # labels are probabilities
                    weights = topk_probs
                # NOTE: argmax is required because np.random.multinomial "counts" the number of outcomes
                # so if multinomial of 5 values draws the 4th value and 1 trial is used the outcome would
                # be [0, 0, 0, 1, 0] -> with argmax -> 4
                choice = rng.multinomial(1, weights).argmax()
            return topk_idxs[choice]

        # hard labels
        assert self.tau is None
        if self.pseudo_labels.ndim == 1:
            assert self.threshold is None, "provided pseudo labels have no probabilities -> can't apply threshold"
            return self.pseudo_labels[idx]
        elif self.pseudo_labels.ndim == 2:
            if self.threshold is None:
                return self.pseudo_labels[idx].argmax()
            else:
                pseudo_label_probs = self.pseudo_labels[idx].softmax(dim=0)
                argmax = pseudo_label_probs.argmax()
                if pseudo_label_probs[argmax] > self.threshold:
                    return argmax
                return -1
        else:
            raise NotImplementedError

    def getall_class(self):
        if self.splits > 1:
            raise NotImplementedError
        if self.pseudo_labels.ndim == 1:
            return self.pseudo_labels.tolist()
        raise NotImplementedError
