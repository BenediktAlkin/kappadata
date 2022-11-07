import torch
from torchvision.transforms.functional import to_tensor
from kappadata.utils.pos_embed import get_2d_sincos_pos_embed
import einops

class ImagePosEmbedSincos:
    def __init__(self, dim=4):
        assert dim % 4 == 0
        self.dim = dim

    def __call__(self, x):
        if not torch.is_tensor(x):
            x = to_tensor(x)
        _, h, w = x.shape
        pos_embed = get_2d_sincos_pos_embed(embed_dim=self.dim, h=h, w=w)
        return torch.concat([x, pos_embed])

