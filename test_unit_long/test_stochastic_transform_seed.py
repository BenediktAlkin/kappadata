import numpy as np
import unittest
from kappadata.transforms import KDStochasticTransform
from tests_util.datasets.x_dataset import XDataset
from torch.utils.data import DataLoader
from kappadata.wrappers import ModeWrapper, XTransformWrapper
import torch

class TestStochasticTransformSeed(unittest.TestCase):
    class _TestTransform(KDStochasticTransform):
        def __call__(self, x, ctx=None):
            return self.rng.random()

    def test_single_worker_noseed(self):
        dataset = XTransformWrapper(dataset=XDataset(torch.arange(10)), transform=self._TestTransform())
        dataset = ModeWrapper(dataset, mode="x")
        values = torch.concat([x for x in DataLoader(dataset, batch_size=2)])
        self.assertEqual(values.unique().numel(), values.numel())

    def test_single_worker_globalseed(self):
        for _ in range(2):
            np.random.seed(0)
            dataset = XTransformWrapper(dataset=XDataset(torch.arange(10)), transform=self._TestTransform())
            dataset = ModeWrapper(dataset, mode="x")
            values = torch.concat([x for x in DataLoader(dataset, batch_size=2)])
            expected = [
                0.38255389159742137,
                0.34776831374136297,
                0.7534087540864453,
                0.5815352814832978,
                0.6920447974218022,
                0.3324638559200749,
                0.7439437217563455,
                0.6524144695739501,
                0.4358178202087156,
                0.3025380253474623,
            ]
            self.assertEqual(expected, values.tolist())

    def test_two_worker_noseed(self):
        dataset = XTransformWrapper(dataset=XDataset(torch.arange(10)), transform=self._TestTransform())
        dataset = ModeWrapper(dataset, mode="x")
        dataloader = DataLoader(dataset, batch_size=2, num_workers=2, worker_init_fn=dataset.worker_init_fn)
        values = torch.concat([x for x in dataloader])
        self.assertEqual(values.unique().numel(), values.numel())


    def test_two_worker_globalseed(self):
        for _ in range(2):
            torch.manual_seed(0)
            dataset = XTransformWrapper(dataset=XDataset(torch.arange(10)), transform=self._TestTransform())
            dataset = ModeWrapper(dataset, mode="x")
            dataloader = DataLoader(dataset, batch_size=2, num_workers=2, worker_init_fn=dataset.worker_init_fn)
            values = torch.concat([x for x in dataloader])
            expected = [
                0.05265565657170268,
                0.5856545413116812,
                0.5245641455144165,
                0.9032732387757539,
                0.7345538141574777,
                0.9076975596537473,
                0.2264209460224459,
                0.9893990449288441,
                0.7417763462601573,
                0.7998301927398731,
            ]
            self.assertEqual(expected, values.tolist())

    def test_is_num_worker_independent_with_seed(self):
        dataset = XTransformWrapper(dataset=XDataset(torch.arange(10)), transform=self._TestTransform(), seed=0)
        dataset = ModeWrapper(dataset, mode="x")
        dataloader0 = DataLoader(dataset, batch_size=2)
        dataloader1 = DataLoader(dataset, batch_size=2, num_workers=2, worker_init_fn=dataset.worker_init_fn)
        values0 = torch.concat([x for x in dataloader0])
        values1 = torch.concat([x for x in dataloader1])
        self.assertEqual(values0.tolist(), values1.tolist())
