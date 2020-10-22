from tqdm import tqdm
import numpy as np
from skimage.io import imread
from skimage.transform import resize
from scipy.stats import binned_statistic_2d


def _load_and_normalize(filename: str,
                        output_shape: tuple = (64, 64)):

    """ load an image, reshape to output_shape and normalize """

    # reshape to a certain image size
    image = resize(imread(filename), output_shape, preserve_range=True)
    n_pixels = np.prod(output_shape)
    n_channels = image.shape[-1]

    a_std = lambda d: np.max([np.std(d), 1. / np.sqrt(n_pixels)])
    nrm = lambda d: np.clip((d - np.mean(d)) / a_std(d), -4., 4.)

    for dim in range(n_channels):
        image[..., dim] = nrm(image[..., dim])

    # TODO(arl): ????
    image = np.clip(255. * ((image + 1.) / 5.), 0, 255)
    return image


class ManifoldProjection2D:
    """ ManifoldProjection2D


    Params:
        image_files: list
        output_shape:
        bins: int
        components:
        preload_images: bool

    """
    def __init__(self,
                 image_files: list,
                 output_shape: tuple = (64, 64),
                 preload_images: bool = True):

        self._output_shape = output_shape
        self._image_files = image_files

        # preload the images
        if preload_images:
            self._images = [self._get_image(file) for file in tqdm(image_files)]
        else:
            self._images = []

    def _get_image(self, filename):
        """ grab an image and resize it """
        return _load_and_normalize(filename, output_shape=self._output_shape)

    def __call__(self,
                 manifold: np.ndarray,
                 bins: int = 32,
                 components: tuple = (0, 1)):

        """ build the projection """

        assert manifold.shape[0] == len(self._image_files)

        # bin the manifold
        s, xe, ye, bn = binned_statistic_2d(manifold[:, 0], manifold[:, 1], [],
                                            bins=bins, statistic='count',
                                            expand_binnumbers=True)

        bxy = zip(bn[0, :].tolist(), bn[1, :].tolist())

        # make a lookup dictionary
        grid = {}
        for idx, b in enumerate(bxy):
            if b not in grid:
                grid[b] = []

            if self._images:
                grid[b].append(self._images[idx])
            else:
                if not grid[b]:
                    grid[b].append(self._get_image(self._image_files[idx]))

        # now make the grid image
        full_bins = [int(b) for b in self._output_shape]
        half_bins = [b // 2 for b in self._output_shape]
        imgrid = np.zeros(((full_bins[0] + 1) * bins + half_bins[0],
                           (full_bins[1] + 1) * bins + half_bins[1], 3),
                          dtype='uint8')

        # build it
        for xy, images in tqdm(grid.items()):

            stack = np.stack(images, axis=0)
            im = np.mean(stack, axis=0)

            xx, yy = xy
            blockx = slice(xx * full_bins[0] - half_bins[0],
                           (xx + 1) * full_bins[0] - half_bins[0], 1)
            blocky = slice(yy * full_bins[1] - half_bins[1],
                           (yy + 1) * full_bins[1] - half_bins[1], 1)

            imgrid[blockx, blocky, :] = im

        # return the extent, i.e. the mapping back to the components of the
        # manifold
        extent = [min(xe), max(xe), min(ye), max(ye)]

        return imgrid, extent


if __name__ == '__main__':
    pass
