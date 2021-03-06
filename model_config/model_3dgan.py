"""
    3d Multi Modal GAN
"""
from __future__ import division

from six.moves import xrange
from eval.evaluation_mrbrain import evaluate
from lib.operations import *
from lib.utils import *
from preprocess.preprocess_mrbrains import *
from tf_logging.tf_logger import Logger


F = tf.app.flags.FLAGS



class model(object):
    def __init__(self, sess, patch_shape, extraction_step):
        self.sess = sess
        self.patch_shape = patch_shape
        self.extraction_step = extraction_step
        self.g_bns = [batch_norm(name='g_bn{}'.format(i, )) for i in range(4)]
        if F.badGAN:
            self.e_bns = [batch_norm(name='e_bn{}'.format(i, )) for i in range(3)]

    def discriminator(self, patch, reuse=False):
        """
        Parameters:
        * patch - input image for the network
        * reuse - boolean variable to reuse weights
        Returns:
        * logits
        * softmax of logits
        * features extracted from encoding path
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

            return h14, tf.nn.softmax(h14), h6

    def generator(self, z, phase):
        """
        Parameters:
        * z - Noise vector for generating 3D patches
        * phase - boolean variable to represent phase of operation of batchnorm
        Returns:
        * generated 3D patches
        """
        with tf.variable_scope('G') as scope:
            sh1, sh2, sh3, sh4 = int(self.patch_shape[0] / 16), int(self.patch_shape[0] / 8), \
                                 int(self.patch_shape[0] / 4), int(self.patch_shape[0] / 2)

            h0 = linear(z, sh1 * sh1 * sh1 * 512, 'g_h0_lin')
            h0 = tf.reshape(h0, [F.batch_size, sh1, sh1, sh1, 512])
            h0 = relu(self.g_bns[0](h0, phase))

            h1 = relu(self.g_bns[1](deconv3d(h0, [F.batch_size, sh2, sh2, sh2, 256],
                                             name='g_h1_deconv'), phase))

            h2 = relu(self.g_bns[2](deconv3d(h1, [F.batch_size, sh3, sh3, sh3, 128],
                                             name='g_h2_deconv'), phase))

            h3 = relu(self.g_bns[3](deconv3d(h2, [F.batch_size, sh4, sh4, sh4, 64],
                                             name='g_h3_deconv'), phase))

            h4 = deconv3d_WN(h3, F.num_mod, name='g_h4_deconv')

            return tf.nn.tanh(h4)

    def encoder(self, patch, phase):
        """
        Parameters:
        * patch - patches generated from the generator
        * phase - boolean variable to represent phase of operation of batchnorm
        Returns:
        * splitted logits
        """
        with tf.variable_scope('E') as scope:
            h0 = relu(self.e_bns[0](conv3d(patch, 128, 5, 5, 5, 2, 2, 2, name='e_h0_conv'), phase))
            h1 = relu(self.e_bns[1](conv3d(h0, 256, 5, 5, 5, 2, 2, 2, name='e_h1_conv'), phase))
            h2 = relu(self.e_bns[2](conv3d(h1, 512, 5, 5, 5, 2, 2, 2, name='e_h2_conv'), phase))

            h2 = tf.reshape(h2, [h2.shape[0], h2.shape[1] * h2.shape[2] * h2.shape[3] * h2.shape[4]])
            h3 = linear_WN(h2, F.noise_dim * 2, 'e_h3_lin')

            h3 = tf.split(h3, 2, 1)
            return h3

    """
    Defines the Few shot GAN U-Net model and the corresponding losses
  
    """

    def build_model(self):

        # Placeholder for labelled patches
        self.patches_lab = tf.placeholder(tf.float32, [F.batch_size, self.patch_shape[0],
                                                       self.patch_shape[1], self.patch_shape[2], F.num_mod],
                                          name='real_images_l')

        # Placeholder for unlabelled patches
        self.patches_unlab = tf.placeholder(tf.float32, [F.batch_size, self.patch_shape[0],
                                                         self.patch_shape[1], self.patch_shape[2], F.num_mod],
                                            name='real_images_unl')

        # Placeholder for noise
        self.z_gen = tf.placeholder(tf.float32, [None, F.noise_dim], name='noise')

        # Placeholder for labels
        self.labels = tf.placeholder(tf.uint8, [F.batch_size, self.patch_shape[0], self.patch_shape[1],
                                                self.patch_shape[2]], name='image_labels')
        # TODO : Figure out
        self.phase = tf.placeholder(tf.bool)

        # To make one hot of labels
        self.labels_1hot = tf.one_hot(self.labels, depth=F.num_classes)

        # To generate samples from noise
        self.patches_fake = self.generator(self.z_gen, self.phase)

        # Forward pass through network with different kinds of training patches
        self.D_logits_lab, self.D_probdist, _ = self.discriminator(self.patches_lab, reuse=False)
        self.D_logits_unlab, _, self.features_unlab = self.discriminator(self.patches_unlab, reuse=True)
        self.D_logits_fake, _, self.features_fake = self.discriminator(self.patches_fake, reuse=True)

        # To obtain Validation Output
        self.Val_output = tf.argmax(self.D_probdist, axis=-1)

        # Supervised loss
        # Weighted cross entropy loss (You can play with these values)
        # Weights of different class are: Background- 0.33, CSF- 1.5, GM- 0.83, WM- 1.33
        # class_weights = tf.constant([[0.33, 1.5, 0.83, 1.33]])
        class_weights = tf.constant([[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]])
        weights = tf.reduce_sum(class_weights * self.labels_1hot, axis=-1)
        unweighted_losses = tf.nn.softmax_cross_entropy_with_logits_v2(logits=self.D_logits_lab,
                                                                       labels=self.labels_1hot)
        weighted_losses = unweighted_losses * weights
        self.d_loss_lab = tf.reduce_mean(weighted_losses)

        # Unsupervised loss
        self.unl_lsexp = tf.reduce_logsumexp(self.D_logits_unlab, -1)
        # Fake loss
        self.fake_lsexp = tf.reduce_logsumexp(self.D_logits_fake, -1)

        # Unlabeled loss
        self.true_loss = - F.tlw * tf.reduce_mean(self.unl_lsexp) + F.tlw * tf.reduce_mean(
            tf.nn.softplus(self.unl_lsexp))
        # Fake loss
        self.fake_loss = F.flw * tf.reduce_mean(tf.nn.softplus(self.fake_lsexp))
        self.d_loss_unlab = self.true_loss + self.fake_loss

        # Total discriminator loss
        self.d_loss = self.d_loss_lab + self.d_loss_unlab

        # Feature matching loss
        self.g_loss_fm = tf.reduce_mean(tf.abs(tf.reduce_mean(self.features_unlab, 0) \
                                               - tf.reduce_mean(self.features_fake, 0)))

        if F.badGAN:
            # Mean and standard deviation for variational inference loss
            self.mu, self.log_sigma = self.encoder(self.patches_fake, self.phase)
            # Generator Loss via variational inference
            self.vi_loss = gaussian_nll(self.mu, self.log_sigma, self.z_gen)
            # Total Generator Loss
            self.g_loss = self.g_loss_fm + F.vi_weight * self.vi_loss
        else:
            # Total Generator Loss
            self.g_loss = self.g_loss_fm

        t_vars = tf.trainable_variables()

        # define the trainable variables
        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]
        if F.badGAN:
            self.e_vars = [var for var in t_vars if 'e_' in var.name]

        self.saver = tf.train.Saver(max_to_keep=None)

    """
    Train function
    Defines learning rates and optimizers.
    Performs Network update and saves the losses
    """

    def train(self):
        # Instantiate tensorflow logger
        self.logger = Logger(model_name='mr_brain', data_name="mrbrains", log_path="tf_logs/"+F.tf_logs)

        # Instantiate the dataset class
        data = dataset_badGAN(num_classes=F.num_classes, extraction_step=self.extraction_step,
                              number_images_training=F.number_train_images, batch_size=F.batch_size,
                              patch_shape=self.patch_shape, number_unlab_images_training=F.number_train_unlab_images,
                              data_directory=F.data_directory)

        # Optimizer operations
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            d_optim = tf.train.AdamOptimizer(F.learning_rate_D, beta1=F.beta1D) \
                .minimize(self.d_loss, var_list=self.d_vars)
            g_optim = tf.train.AdamOptimizer(F.learning_rate_G, beta1=F.beta1G) \
                .minimize(self.g_loss, var_list=self.g_vars)
            if F.badGAN:
                e_optim = tf.train.AdamOptimizer(F.learning_rate_E, beta1=F.beta1E) \
                    .minimize(self.g_loss, var_list=self.e_vars)

        tf.global_variables_initializer().run()

        # Load checkpoints if required
        if F.load_chkpt:
            try:
                load_model(F.checkpoint_dir, self.sess, self.saver)
                print("\n [*] Checkpoint loaded succesfully!")
            except:
                print("\n [!] Checkpoint loading failed!")
        else:
            print("\n [*] Checkpoint load not required.")

        # Load the validation data
        patches_val, labels_val_patch, labels_val = preprocess_dynamic_lab(F.data_directory,
                                                                           F.num_classes, self.extraction_step,
                                                                           self.patch_shape,
                                                                           F.number_train_images, validating=F.training,
                                                                           testing=F.testing,
                                                                           num_images_testing=F.number_test_images)

        predictions_val = np.zeros((patches_val.shape[0], self.patch_shape[0], self.patch_shape[1],
                                    self.patch_shape[2]), dtype="uint8")
        max_par = 0.0
        for epoch in xrange(int(F.epoch)):
            idx = 0
            batch_iter_train = data.batch_train()
            total_val_loss = 0
            total_train_loss_CE = 0
            total_train_loss_UL = 0
            total_train_loss_FK = 0
            total_gen_FMloss = 0

            for patches_lab, patches_unlab, labels in batch_iter_train:
                # Network update
                sample_z_gen = np.random.uniform(-1, 1, [F.batch_size, F.noise_dim]).astype(np.float32)

                _ = self.sess.run(d_optim, feed_dict={self.patches_lab: patches_lab, self.patches_unlab: patches_unlab,
                                                      self.z_gen: sample_z_gen, self.labels: labels, self.phase: True})

                if F.badGAN:
                    _, _ = self.sess.run([e_optim, g_optim],
                                         feed_dict={self.patches_unlab: patches_unlab, self.z_gen: sample_z_gen,
                                                    self.z_gen: sample_z_gen, self.phase: True})
                else:
                    _ = self.sess.run(g_optim, feed_dict={self.patches_unlab: patches_unlab, self.z_gen: sample_z_gen,
                                                          self.z_gen: sample_z_gen, self.phase: True})

                feed_dict = {self.patches_lab: patches_lab, self.patches_unlab: patches_unlab,
                             self.z_gen: sample_z_gen, self.labels: labels, self.phase: True}

                # Evaluate losses for plotting/printing purposes
                d_loss_lab = self.d_loss_lab.eval(feed_dict)
                d_loss_unlab_true = self.true_loss.eval(feed_dict)
                d_loss_unlab_fake = self.fake_loss.eval(feed_dict)
                g_loss_fm = self.g_loss_fm.eval(feed_dict)

                total_train_loss_CE = total_train_loss_CE + d_loss_lab
                total_train_loss_UL = total_train_loss_UL + d_loss_unlab_true
                total_train_loss_FK = total_train_loss_FK + d_loss_unlab_fake
                total_gen_FMloss = total_gen_FMloss + g_loss_fm

                idx += 1
                if F.badGAN:
                    vi_loss = self.vi_loss.eval(feed_dict)
                    print((
                              "Epoch:[%2d] [%4d/%4d] Labeled loss:%.4f Unlabeled loss:%.4f Fake loss:%.4f Generator FM loss:%.8f Generator VI loss:%.8f\n") %
                          (epoch, idx, data.num_batches, d_loss_lab, d_loss_unlab_true, d_loss_unlab_fake, g_loss_fm,
                           vi_loss))
                else:
                    print((
                              "Epoch:[%2d] [%4d/%4d] Labeled loss:%.4f Unlabeled loss:%.4f Fake loss:%.4f Generator loss:%.8f \n") %
                          (epoch, idx, data.num_batches, d_loss_lab, d_loss_unlab_true, d_loss_unlab_fake, g_loss_fm))

            # Save model (Current Checkpoint)
            save_model(F.checkpoint_dir, self.sess, self.saver)

            # Save checkpoint after every 20 epochs
            if epoch % 20 == 0:
                if not os.path.exists(F.checkpoint_base + "/" + str(epoch)):
                    os.makedirs(F.checkpoint_base + "/" + str(epoch))
                    save_model(F.checkpoint_base + "/" + str(epoch), self.sess, self.saver)

            avg_train_loss_CE = total_train_loss_CE / (idx * 1.0)
            avg_train_loss_UL = total_train_loss_UL / (idx * 1.0)
            avg_train_loss_FK = total_train_loss_FK / (idx * 1.0)
            avg_gen_FMloss = total_gen_FMloss / (idx * 1.0)

            print('\n\n')

            total_batches = int(patches_val.shape[0] / F.batch_size)
            print("Total number of batches for validation: ", total_batches)

            # Prediction of validation patches
            for batch in range(total_batches):
                patches_feed = patches_val[batch * F.batch_size:(batch + 1) * F.batch_size, :, :, :, :]
                labels_feed = labels_val_patch[batch * F.batch_size:(batch + 1) * F.batch_size, :, :, :]
                feed_dict = {self.patches_lab: patches_feed,
                             self.labels: labels_feed, self.phase: False}
                preds = self.Val_output.eval(feed_dict)
                val_loss = self.d_loss_lab.eval(feed_dict)

                predictions_val[batch * F.batch_size:(batch + 1) * F.batch_size, :, :, :] = preds
                print(("Validated Patch:[%8d/%8d]") % (batch, total_batches))
                total_val_loss = total_val_loss + val_loss

            # To compute average patchvise validation loss(cross entropy loss)
            avg_val_loss = total_val_loss / (total_batches * 1.0)

            print("All validation patches Predicted")

            print("Shape of predictions_val, min and max:", predictions_val.shape, np.min(predictions_val),
                  np.max(predictions_val))

            # To stitch back the patches into an entire image
            val_image_pred = recompose3D_overlap(predictions_val, 220, 220, 48, self.extraction_step[0],
                                                 self.extraction_step[1], self.extraction_step[2])
            val_image_pred = val_image_pred.astype('uint8')

            print("Shape of Predicted Output Groundtruth Images:", val_image_pred.shape,
                  np.unique(val_image_pred),
                  np.unique(labels_val),
                  np.mean(val_image_pred), np.mean(labels_val))

            # Save the predicted image
            save_image(F.results_dir, val_image_pred[0], 70)

            #pred2d = np.reshape(val_image_pred, (val_image_pred.shape[0] * 220 * 220 * 48))
            #lab2d = np.reshape(labels_val, (labels_val.shape[0] * 220 * 220 * 48))

            # For printing the validation results
            # F1_score = f1_score(lab2d, pred2d, [0, 1, 2, 3, 4, 5, 6, 7, 8], average=None)
            # print("Validation F1 Score.... ")
            # print("Background:", F1_score[0])
            # print("Cortical Gray Matter:", F1_score[1])
            # print("Basal ganglia:", F1_score[2])
            # print("White matter:", F1_score[3])
            # print("White matter lesions:", F1_score[4])
            # print("Cerebrospinal fluid in the extracerebral space:", F1_score[5])
            # print("Ventricles:", F1_score[6])
            # print("Cerebellum:", F1_score[7])
            # print("Brain stem:", F1_score[8])

            dice_score, hausdorff_dist, vol_sim = evaluate(os.path.join(F.results_dir, 'result_70.nii.gz'),
                                                           os.path.join(F.data_directory + "/val/70", 'segm.nii.gz'))

            # To Save the best model
            if (max_par < (dice_score[1] + dice_score[2] + dice_score[3] + dice_score[4] + dice_score[5] + dice_score[6] + dice_score[7] + dice_score[8])):
                max_par = (dice_score[1] + dice_score[2] + dice_score[3] + dice_score[4] + dice_score[5] + dice_score[6] + dice_score[7] + dice_score[8])
                save_model(F.best_checkpoint_dir, self.sess, self.saver)
                print("Best checkpoint got updated from validation results.")

            # To save the losses for plotting
            print("Average Validation Loss:", avg_val_loss)
            self.logger.log_loss(mode='val_loss', loss=avg_val_loss, epoch=epoch + 1)
            self.logger.log_loss(mode='train_ce', loss=avg_train_loss_CE, epoch=epoch + 1)
            self.logger.log_loss(mode='train_ul', loss=avg_train_loss_UL, epoch=epoch + 1)
            self.logger.log_loss(mode='train_fk', loss=avg_train_loss_FK, epoch=epoch + 1)
            self.logger.log_loss(mode='train_fm', loss=avg_gen_FMloss, epoch=epoch + 1)
            self.logger.log_segmentation_metrics(mode='scores', dice_score=dice_score, hausdorff_dist=hausdorff_dist,
                                                 vol_sim=vol_sim, epoch=epoch + 1)

        return
