import os
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import tensorflow as tf

# TODO(arl): allow depth for volumetric data
DIMENSIONS = ["height", "width", "channels"]


def _int64_feature(value):
    return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))


def _bytes_feature(value):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def _float_feature(value):
    return tf.train.Feature(float_list=tf.train.FloatList(value=[value]))


def write_dataset(
    filename: str, images: np.ndarray, labels: Optional[np.ndarray] = None
):
    """Write out a TF record of image data for training models.

    Parameters
    ----------
    filename : str
        The filename of the TFRecordFile.
    images : np.ndarray
        An array of images of the format N(D)HWC.
    labels : np.ndarray, optional
        An array of labels.
    """

    if not filename.endswith(".tfrecord"):
        filename = f"{filename}.tfrecord"

    assert images.dtype in (
        np.uint8,
        np.uint16,
    )
    assert images.ndim > 2 and images.ndim < 6

    if labels is not None:
        assert images.shape[0] == labels.shape[0]

    with tf.io.TFRecordWriter(filename) as writer:

        for idx, data in enumerate(images):
            feature = {
                "train/image": _bytes_feature(data.tostring()),
                "train/width": _int64_feature(data.shape[1]),
                "train/height": _int64_feature(data.shape[0]),
                "train/channels": _int64_feature(data.shape[-1]),
            }

            if labels is not None:
                label = labels[idx]
                feature.update({"train/label": _int64_feature(label)})

            features = tf.train.Features(feature=feature)
            example = tf.train.Example(features=features)

            # write out the serialized features
            writer.write(example.SerializeToString())


def parse_tfrecord(
    serialized_example,
    output_shape: Optional[tuple] = None,
    read_label: bool = False,
    read_weights: bool = False,
):
    """Parse input images and return the one_hot label encoding.

    Parameters
    ----------
    serialized_example : tf.Tensor
        The serialized example to be parsed.
    output_shape : tuple, None
        Optional parameter to non-dynamically define output shape. If none, the
        shape is determined from the dimensions stored in the TFRecord.
    read_label : bool
        Read a label encoded in the file.
    read_weights : bool
        Read weights encoded in the example.

    Returns
    -------
    image : tf.Tensor
        The image as a tf.float32 tensor.
    """

    feature = {
        f"train/{dim}": tf.io.FixedLenFeature([], tf.int64) for dim in DIMENSIONS
    }
    feature.update({"train/image": tf.io.FixedLenFeature([], tf.string)})

    if read_label:
        feature.update({"train/label": tf.io.FixedLenFeature([], tf.int64)})

    features = tf.io.parse_single_example(
        serialized=serialized_example, features=feature
    )

    # convert the image data from string back to the numbers
    image_raw = tf.io.decode_raw(features["train/image"], tf.uint8)

    # get the image dimensions
    if output_shape is None:
        output_shape = [features[f"train/{dim}"] for dim in DIMENSIONS]

    image = tf.cast(tf.reshape(image_raw, output_shape), tf.float32)

    if read_label:
        label = features["train/label"]
        return image, label
    else:
        return image


def per_channel_normalize(x: tf.Tensor) -> tf.Tensor:
    """Independently normalize each channel of an image to zero mean, unit
    variance."""
    stack = []
    for dim in range(x.shape[-1]):
        channel = tf.expand_dims(x[..., dim], -1)
        normalized = tf.squeeze(tf.image.per_image_standardization(channel))
        stack.append(normalized)
    x = tf.stack(stack, axis=-1)
    x = tf.clip_by_value(x, -4.0, 4.0)
    return x


def build_dataset(files: Union[List[os.PathLike], os.PathLike], **kwargs):
    """Build a TF Dataset from a list of TFRecordFiles. Map the parser to it.

    Parameters
    ----------
    files : str, list[str]
        The list of TFRecord files to use for the dataset.

    Returns
    -------
    dataset : tf.data.Dataset
        The TF dataset.
    """

    # parse the input
    if not isinstance(files, list):
        fn, ext = os.path.splitext(files)
        if ext != "tfrecord":
            pth = Path(files)
            files = [pth / f for f in os.listdir(files) if f.endswith(".tfrecord")]

    dataset = tf.data.TFRecordDataset(files)
    dataset = dataset.map(lambda x: parse_tfrecord(x, **kwargs), num_parallel_calls=8)
    return dataset
