import os

import tensorflow as tf
import pprint
from model_config.model_3dgan import model
from test_gan import test

# Define flags
flags = tf.app.flags
flags.DEFINE_integer("epoch", 100, "Number of training epochs (default: 100)")
flags.DEFINE_float("learning_rate_D", 0.0001, "Learning rate of Adam optimizer for Discriminator (default: 0.0001)")
flags.DEFINE_float("learning_rate_G", 0.0001, "Learning rate of Adam optimizer for Generator (default: 0.0001)")
flags.DEFINE_float("learning_rate_E", 0.0001, "Learning rate of Adam optimizer for Encoder (default: 0.0001)")
flags.DEFINE_float("beta1D", 0.5, "Momentum term of Adam optimizer for Discriminator (default: 0.5)")
flags.DEFINE_float("beta1G", 0.5, "Momentum term of Adam optimizer for Generator (default: 0.5)")
flags.DEFINE_float("beta1E", 0.5, "Momentum term of Adam optimizer for Encoder (default: 0.5)")

flags.DEFINE_float("gpu_frac", 1.0, "Gpu fraction")
flags.DEFINE_float("tlw", 0.5, "True loss weight")
flags.DEFINE_float("flw", 0.5, "Fake loss weight")
flags.DEFINE_float("vi_weight", 0.01, "Weight of variational inference loss")

flags.DEFINE_integer("number_train_images", 4, "No. of labeled images for training")
flags.DEFINE_integer("gpu", 0, "GPU id")
flags.DEFINE_integer("number_train_unlab_images", 4, "No. of unlabeled images for training")
flags.DEFINE_integer("number_test_images", 2, "No. of images for testing")

flags.DEFINE_string("data_directory", "data/mrbrains_normalized", "Directory name containing the dataset")
flags.DEFINE_string("dataset", "mrbrains_normalized", "Dataset name")
flags.DEFINE_string("checkpoint_dir", "checkpoint/3d_gan_normalized_val70/current", "Directory name to save the checkpoints [checkpoint]")
flags.DEFINE_string("checkpoint_base", "checkpoint/3d_gan_normalized_val70/epochs", "Directory name to save the checkpoints epochs [checkpoint]")
flags.DEFINE_string("best_checkpoint_dir", "checkpoint/3d_gan_normalized_val70/best","Directory name to save the best checkpoints [checkpoint]")
flags.DEFINE_string("results_dir", "results/3d_gan_normalized_val70/", "Directory name to save the results [results]")
flags.DEFINE_string("tf_logs", "3d_gan_normalized_val70/", "Directory name to save tensorflow logs")

flags.DEFINE_boolean("load_chkpt", False, "True for loading saved checkpoint")
flags.DEFINE_boolean("training", False, "True for Training ")
flags.DEFINE_boolean("testing", False, "True for Testing ")
flags.DEFINE_boolean("badGAN", False, "True if you want to run badGAN based model ")

flags.DEFINE_integer("batch_size", 32, "The size of batch images")

flags.DEFINE_integer("num_mod", 2, "Number of modalities of the input 3-D image")
flags.DEFINE_integer("num_classes", 9, "Number of output classes to segment")
flags.DEFINE_integer("noise_dim", 200, "Dimension of noise vector")

FLAGS = flags.FLAGS

os.environ['CUDA_VISIBLE_DEVICES'] = str(FLAGS.gpu)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

pprint.pprint("Running with the following parameters:")
parameter_value_map = {}
for key in FLAGS.__flags.keys():
  parameter_value_map[key] = FLAGS.__flags[key].value
print("Parameters: {}".format(parameter_value_map))

def main(_):
    # Create required directories
    if not os.path.exists(FLAGS.checkpoint_dir):
        os.makedirs(FLAGS.checkpoint_dir)

    if not os.path.exists(FLAGS.results_dir):
        os.makedirs(FLAGS.results_dir)

    if not os.path.exists(FLAGS.best_checkpoint_dir):
        os.makedirs(FLAGS.best_checkpoint_dir)

    # To configure the GPU fraction
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=FLAGS.gpu_frac)

    # Parameters of extracted training and testing patches
    patch_shape = (32, 32, 32)
    extraction_step = (4, 4, 4)
    testing_extraction_shape = (4, 4, 4)

    if FLAGS.training:
        # For training the network
        with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
            network = model(sess, patch_shape, extraction_step)
            network.build_model()
            network.train()
    if FLAGS.testing:
        # For testing the trained network
        test(patch_shape, testing_extraction_shape)


if __name__ == '__main__':
    tf.app.run()
