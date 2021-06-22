from enum import Enum
from typing import List, Optional

from tensorflow import keras as K

from ..layers import ConvBlock2D


class SkipConnection(Enum):
    """Skip connections for UNet."""

    ELEMENTWISE_ADD = K.layers.Add()
    ELEMENTWISE_MULTIPLY = K.layers.Multiply()
    CONCATENATE = K.layers.Concatenate(axis=-1)
    NONE = lambda x: x[0]

    def __call__(self, inputs):
        return self.value(inputs)


class UNet(K.Model):
    """ UNet

    A UNet class for image segmentation. This implementation differs in that we
    pad each convolution such that the output following convolution is the same
    size as the input. Also, bridges are elementwise operations of the filters
    to approach a residual-net architecture (resnet), although this can be
    changed by the user.  The skip property allows different skip connection
    types to be specified:
        - elementwise_add
        - elementwise_multiply
        - concatenate
        - None (no bridge information, resembles an autoencoder)

    ** The final layer does not have an activation function. **

    Parameters
    ----------
    convolution : K.layers.Layer
        A convolution layer.
    downsampling : K.layers.Layer
        A downsampling layer.
    upsampling : K.layers.Layer
        An upsampling layer.
    layers : list of int
        A list of filters for each layer.
    skip : str
        The skip connection type.
    output_filters : int
        The number of output filters.
    name : str
        The name of the network.

    Notes
    -----
    Based on the original publications:

        U-Net: Convolutional Networks for Biomedical Image Segmentation
        Olaf Ronneberger, Philipp Fischer and Thomas Brox
        http://arxiv.org/abs/1505.04597

        3D U-Net: Learning Dense Volumetric Segmentation from Sparse Annotation
        Ozgun Cicek, Ahmed Abdulkadir, Soeren S. Lienkamp, Thomas Brox
        and Olaf Ronneberger
        https://arxiv.org/abs/1606.06650

        Filter doubling from:
        Rethinking the Inception Architecture for Computer Vision.
        Szegedy C., Vanhoucke V., Ioffe S., Shlens J., Wojn, Z.
        https://arxiv.org/abs/1512.00567
    """

    def __init__(
        self,
        convolution: K.layers.Layer = ConvBlock2D,
        downsampling: Optional[K.layers.Layer] = K.layers.MaxPooling2D,
        upsampling: Optional[K.layers.Layer] = K.layers.UpSampling2D,
        layers: List[int] = [8, 16, 32],
        output_filters: int = 1,
        skip: str = "concatenate",
        name: str = "unet",
        **kwargs,
    ):

        super().__init__(name=name, **kwargs)

        # set the skip connection here
        if skip.upper() not in SkipConnection._member_names_:
            raise ValueError(f"Skip connection {skip} not recognized.")

        self._skips = [K.layers.Concatenate(axis=-1) for i in range(len(layers) - 1)]

        # set up the convolutions
        self._encoder = [
            convolution(filters=k, name=f"Encoder{i}") for i, k in enumerate(layers)
        ]
        self._decoder = [
            convolution(filters=k, name=f"Decoder{i}")
            for i, k in enumerate(layers[:-1])
        ]

        self._decoder_output = convolution(
            filters=output_filters, kernel_size=1, activation="linear", name="Output"
        )

        assert len(self._encoder) == len(self._decoder) + 1
        assert len(self._skips) == len(self._decoder)

        # set up the up/downsampling
        # TODO(arl): these may already be instantiated with custom params
        # TODO(arl): if using a transpose convolution, we need to set the number of filters
        self._downsamplers = [downsampling() for i in range(len(layers) - 1)]
        self._upsamplers = [upsampling() for i in range(len(layers) - 1)]

    def call(self, x, training: Optional[bool] = None):
        # build the encoder arm
        skips = []
        for level, conv in enumerate(self._encoder):
            x = conv(x, training=training)
            if conv != self._encoder[-1]:
                skips.append(x)
                x = self._downsamplers[level](x)

        # build the decoder arm using skips
        x = self._upsamplers[-1](x)
        for level, conv in list(enumerate(self._decoder))[::-1]:
            x = self._skips[level]([x, skips[level]])
            x = conv(x, training=training)
            if conv != self._decoder[0]:
                x = self._upsamplers[level - 1](x)

        # final convolution for output
        x = self._decoder_output(x)

        return x
