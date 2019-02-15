from __future__ import division

from sklearn.metrics import f1_score

from lib.operations import *
from lib.utils import *
from preprocess.preprocess_mrbrains import *
from eval.evaluation_metric import evaluate_stats

# sys.path.insert(0, '../preprocess/')
# sys.path.insert(0, '../lib/')


F = tf.app.flags.FLAGS


# Function to save predicted images as .nii.gz file in results folder
def save_image(direc, i, num):
    img = nib.Nifti1Image(i, None)
    imgname = 'result_' + str(num) + '.nii.gz'
    nib.save(img, os.path.join(direc, imgname))


# Same discriminator network as in model file
def trained_dis_network(patch, reuse=False):
    """
    Parameters:
    * patch - input image for the network
    * reuse - boolean variable to reuse weights
    Returns: 
    * softmax of logits 
    """
    with tf.variable_scope('D') as scope:
        if reuse:
            scope.reuse_variables()

        h0 = lrelu(conv3d_WN(patch, 32, name='d_h0_conv'))
        h1 = lrelu(conv3d_WN(h0, 32, name='d_h1_conv'))
        p1 = avg_pool3D(h1)

        h2 = lrelu(conv3d_WN(p1, 64, name='d_h2_conv'))
        h3 = lrelu(conv3d_WN(h2, 64, name='d_h3_conv'))
        p3 = avg_pool3D(h3)

        h4 = lrelu(conv3d_WN(p3, 128, name='d_h4_conv'))
        h5 = lrelu(conv3d_WN(h4, 128, name='d_h5_conv'))
        p5 = avg_pool3D(h5)

        h6 = lrelu(conv3d_WN(p5, 256, name='d_h6_conv'))
        h7 = lrelu(conv3d_WN(h6, 256, name='d_h7_conv'))

        up1 = deconv3d_WN(h7, 256, name='d_up1_deconv')
        up1 = tf.concat([h5, up1], 4)
        h8 = lrelu(conv3d_WN(up1, 128, name='d_h8_conv'))
        h9 = lrelu(conv3d_WN(h8, 128, name='d_h9_conv'))

        up2 = deconv3d_WN(h9, 128, name='d_up2_deconv')
        up2 = tf.concat([h3, up2], 4)
        h10 = lrelu(conv3d_WN(up2, 64, name='d_h10_conv'))
        h11 = lrelu(conv3d_WN(h10, 64, name='d_h11_conv'))

        up3 = deconv3d_WN(h11, 64, name='d_up3_deconv')
        up3 = tf.concat([h1, up3], 4)
        h12 = lrelu(conv3d_WN(up3, 32, name='d_h12_conv'))
        h13 = lrelu(conv3d_WN(h12, 32, name='d_h13_conv'))

        h14 = conv3d_WN(h13, F.num_classes, name='d_h14_conv')

        return tf.nn.softmax(h14)


"""
 Function to test the model and evaluate the predicted images
 Parameters:
 * patch_shape - shape of the patch
 * extraction_step - stride while extracting patches
"""


def test(patch_shape, extraction_step):
    with tf.Graph().as_default():
        test_patches = tf.placeholder(tf.float32, [F.batch_size, patch_shape[0], patch_shape[1],
                                                   patch_shape[2], F.num_mod], name='real_patches')

        # Define the network
        output_soft = trained_dis_network(test_patches, reuse=None)

        # To convert from one hat form
        output = tf.argmax(output_soft, axis=-1)
        print("Output Patch Shape:", output.get_shape())

        # To load the saved checkpoint
        saver = tf.train.Saver()
        with tf.Session() as sess:
            try:
                load_model(F.best_checkpoint_dir, sess, saver)
                print(" Checkpoint loaded succesfully!....\n")
            except:
                print(" [!] Checkpoint loading failed!....\n")
                return

            # Get patches from test images
            patches_test, labels_test = preprocess_dynamic_lab(F.data_directory,
                                                               F.num_classes, extraction_step, patch_shape,
                                                               F.number_train_images, validating=F.training,
                                                               testing=F.testing,
                                                               num_images_testing=F.number_test_images)
            total_batches = int(patches_test.shape[0] / F.batch_size)

            # Array to store the prediction results
            predictions_test = np.zeros((patches_test.shape[0], patch_shape[0], patch_shape[1],
                                         patch_shape[2]))

            print("max and min of patches_test:", np.min(patches_test), np.max(patches_test))

            print("Total number of Batches: ", total_batches)

            # Batch wise prediction
            for batch in range(total_batches):
                patches_feed = patches_test[batch * F.batch_size:(batch + 1) * F.batch_size, :, :, :, :]
                preds = sess.run(output, feed_dict={test_patches: patches_feed})
                predictions_test[batch * F.batch_size:(batch + 1) * F.batch_size, :, :, :] = preds
                print(("Processed_batch:[%8d/%8d]") % (batch, total_batches))

            print("All patches Predicted")

            print("Shape of predictions_test, min and max:", predictions_test.shape, np.min(predictions_test),
                  np.max(predictions_test))

            # To stitch the image back
            images_pred = recompose3D_overlap(predictions_test, 240, 240, 48, extraction_step[0],
                                              extraction_step[1], extraction_step[2])

            print("Shape of Predicted Output Groundtruth Images:", images_pred.shape,
                  np.min(images_pred), np.max(images_pred),
                  np.mean(images_pred), np.mean(labels_test))

            # To save the images
            test_idx = [7, 14]
            for i in range(F.number_test_images):
                # pred2d=np.reshape(images_pred[i],(240*240*48))
                # lab2d=np.reshape(labels_test[i],(240*240*48))
                save_image(F.results_dir, images_pred[i], test_idx[i])

            # Evaluation
            pred2d = np.reshape(images_pred, (images_pred.shape[0] * 240 * 240 * 48))
            lab2d = np.reshape(labels_test, (labels_test.shape[0] * 240 * 240 * 48))

            F1_score = f1_score(lab2d, pred2d, [0, 1, 2, 3, 4, 5, 6, 7, 8], average=None)
            print("Testing Dice Coefficient.... ")
            print("Background:", F1_score[0])
            print("Cortical Gray Matter:", F1_score[1])
            print("Basal ganglia:", F1_score[2])
            print("White matter:", F1_score[3])
            print("White matter lesions:", F1_score[4])
            print("Cerebrospinal fluid in the extracerebral space:", F1_score[5])
            print("Ventricles:", F1_score[6])
            print("Cerebellum:", F1_score[7])
            print("Brain stem:", F1_score[8])



    return