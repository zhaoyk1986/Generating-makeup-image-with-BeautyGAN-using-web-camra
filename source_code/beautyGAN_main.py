import os

os.environ['CUDA_VISIBLE_DEVICES']='1,2'

import tensorflow as tf
from tensorflow.python.client import device_lib
print(device_lib.list_local_devices())
import pickle
import dlib
import cv2
import numpy as np
from scipy.misc import imsave
import os
import time
import random
from model import generate_discriminator
from model import build_generator
import vgg16
import utils
import glob


batch_size = 1
gpu_num = 2
max_images = 1050
pool_size = 50

img_height = 256
img_width = 256
img_layer = 3

to_restore = True
save_training_images = False
to_train = True 
to_test = False
out_path = "./output_ori"
check_dir = "./output/checkpoints_ori/"
load_dir = "imgs3.txt"

def get_latest_model_checkpoint_path(folder, name):
    '''
    Returns the checkpoint with the highest iteration number with a given name
    :param folder: Folder where the checkpoints are saved
    :param name: Name under which you saved the model
    :return: The path to the checkpoint with the latest iteration
    '''

    iteration_nums = []
    for file in glob.glob(os.path.join(folder, '%s*.meta' % name)):

        file = file.split('/')[-1]
        file_base, rest = file.split('.')[0:2]
        it_num = int(file_base.split('-')[-1])

        iteration_nums.append(it_num)

    latest_iteration = np.max(iteration_nums)

    return os.path.join(folder, name + '-' + str(latest_iteration))

class BeautyGAN():
    def __init__(self, prediction=False, check_dir = None):
         
        self.prediction = prediction
        
        if(self.prediction):
            
            self.model_prediction_setup()
            self.saver = tf.train.Saver()

            
            self.sess = tf.Session()
#             model_path = '/tmp2/chunting/makeup/beautyGAN-tf-Implement/output/checkpoints/best/beautyGAN-257'
            model_path = tf.train.latest_checkpoint(check_dir)
            
            self.saver.restore(self.sess, model_path)
            print('restored ', model_path)
            
        else:
            self.input_setup()
            self.model_setup()
        
            init = [tf.local_variables_initializer(),tf.global_variables_initializer()]
            self.saver = tf.train.Saver()
            
    def predict(self, sample, target):
        
        if(not self.prediction):
            print('Not in prediction mode')
            return
           
        fake_A_temp,fake_B_temp = self.sess.run([self.fake_A,self.fake_B],feed_dict={
                self.input_A: sample,
                self.input_B: target
            })
        
        return fake_A_temp,fake_B_temp
          
       
    def input_setup(self):
        """
        dataset_A:non-makeup
        dataset_B:makeup
        :return:
        """
        filename_A = tf.train.match_filenames_once("../all/image_align/non_makeup/*.png")
        self.queue_length_A = tf.size(filename_A)
        filename_B = tf.train.match_filenames_once("../all/image_align/makeup/*.png")
        self.queue_length_B = tf.size(filename_B)

        filename_A_queue = tf.train.string_input_producer(filename_A,shuffle=False)
        filename_B_queue = tf.train.string_input_producer(filename_B,shuffle=False)

        image_reader = tf.WholeFileReader()
        _, image_file_A = image_reader.read(filename_A_queue)
        _, image_file_B = image_reader.read(filename_B_queue)
        self.image_A = tf.subtract(tf.div(tf.image.resize_images(tf.image.decode_jpeg(image_file_A),[256,256]),127.5),1)
        self.image_B = tf.subtract(tf.div(tf.image.resize_images(tf.image.decode_jpeg(image_file_B),[256,256]),127.5),1)
        

    # Modified on 5/6
    def get_mask(self, input_face, detector, predictor,window=5):
        h, w, ch = input_face.shape
        gray = cv2.cvtColor(input_face, cv2.COLOR_BGR2GRAY)
        dets = detector(gray, 1)

        for face in dets:
            shape = predictor(input_face, face)
            temp = []
            for pt in shape.parts():
                temp.append([pt.x, pt.y])
            lip_mask = np.zeros([256, 256])
            eye_mask = np.zeros([256,256])
            face_mask = np.full((256, 256), 255).astype(np.uint8)
            cv2.fillPoly(lip_mask, [np.array(temp[48:60]).reshape((-1, 1, 2))], (255, 255, 255))
            cv2.fillPoly(lip_mask, [np.array(temp[60:68]).reshape((-1, 1, 2))], (0, 0, 0))

            left_left = min(x[0] for x in temp[36:42])
            left_right = max(x[0] for x in temp[36:42])
            left_bottom = min(x[1] for x in temp[36:42])
            left_top = max(x[1] for x in temp[36:42])
            left_rectangle = np.array(
                [[left_left - window, left_top + window], [left_right + window, left_top + window],
                 [left_right + window, left_bottom - window], [left_left - window, left_bottom - window]]
            ).reshape((-1, 1, 2))
            cv2.fillPoly(eye_mask, [left_rectangle], (255, 255, 255))
            cv2.fillPoly(eye_mask, [np.array(temp[36:42]).reshape((-1, 1, 2))], (0, 0, 0))

            right_left = min(x[0] for x in temp[42:48])
            right_right = max(x[0] for x in temp[42:48])
            right_bottom = min(x[1] for x in temp[42:48])
            right_top = max(x[1] for x in temp[42:48])
            right_rectangle = np.array(
                [[right_left - window, right_top + window], [right_right + window, right_top + window],
                 [right_right + window, right_bottom - window], [right_left - window, right_bottom - window]]
            ).reshape((-1, 1, 2))
            cv2.fillPoly(eye_mask, [right_rectangle], (255, 255, 255))
            cv2.fillPoly(eye_mask, [np.array(temp[42:47]).reshape((-1, 1, 2))], (0, 0, 0))

            face_courner = temp[0:16]+temp[26:16:-1]
#             print(face_courner)
            cv2.fillPoly(face_mask, [np.array([[0,0],[0,h],[w,h],[w,0]])],(0, 0, 0))
            cv2.fillPoly(face_mask, [np.array(face_courner).reshape(-1, 1, 2)],(255, 255, 255))
            cv2.polylines(face_mask, [np.array(temp[17:22]).reshape(-1, 1, 2)], False, (0, 0, 0), 7)
            cv2.polylines(face_mask, [np.array(temp[22:27]).reshape(-1, 1, 2)], False, (0, 0, 0), 7)

            cv2.fillPoly(face_mask, [np.array(temp[36:42]).reshape((-1, 1, 2))], (0, 0, 0))
            cv2.fillPoly(face_mask, [np.array(temp[42:48]).reshape((-1, 1, 2))], (0, 0, 0))
            cv2.fillPoly(face_mask, [np.array(temp[48:60]).reshape((-1, 1, 2))], (0, 0, 0))
            
            return lip_mask,eye_mask,face_mask
        


    def input_read(self,sess):
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(coord=coord)

        num_file_A = sess.run(self.queue_length_A)
        num_file_B = sess.run(self.queue_length_B)
        
        print(num_file_A, num_file_B)

        self.fake_images_A = np.zeros((pool_size,1,img_height,img_width,img_layer))
        self.fake_images_B = np.zeros((pool_size,1,img_height,img_width,img_layer))

        self.A_input = np.zeros((num_file_A,batch_size,img_height,img_width,img_layer))
        self.B_input = np.zeros((num_file_B,batch_size,img_height,img_width,img_layer))
        self.A_input_mask = np.zeros((num_file_A,3,img_height,img_width))
        self.B_input_mask = np.zeros((num_file_B,3,img_height,img_width))


        if not os.path.exists(load_dir):
            cur_A = 0
            for i in range(num_file_A):
                image_tensor = sess.run(self.image_A)
                if image_tensor.size==img_width*img_height*img_layer:
                    temp = ((image_tensor+1)*127.5).astype(np.uint8)
                    res = self.get_mask(temp,self.detector,self.predictor)
                    if res!=None:
                        self.A_input[cur_A] = image_tensor.reshape((batch_size, img_height, img_width, img_layer))
                        self.A_input_mask[cur_A][0] = np.equal(res[0],255)
                        self.A_input_mask[cur_A][1] = np.equal(res[1],255)
                        self.A_input_mask[cur_A][2] = np.equal(res[2],255)
                        cur_A+=1

            cur_B = 0
            for i in range(num_file_B):
                image_tensor = sess.run(self.image_B)
                if image_tensor.size==img_width*img_height*img_layer:
                    self.B_input[i] = image_tensor.reshape((batch_size,img_height,img_width,img_layer))
                    temp = ((image_tensor+1)*127.5).astype(np.uint8)
                    res = self.get_mask(temp, self.detector, self.predictor)
                    if res != None:
                        self.B_input[cur_B] = image_tensor.reshape((batch_size, img_height, img_width, img_layer))
                        self.B_input_mask[cur_B][0] = np.equal(res[0],255)
                        self.B_input_mask[cur_B][1] = np.equal(res[1],255)
                        self.B_input_mask[cur_B][2] = np.equal(res[2],255)
                        cur_B += 1

            os.mknod(load_dir)
            fw = open(load_dir,"wb")
            pickle.dump(self.A_input,fw)
            pickle.dump(self.B_input,fw)
            pickle.dump(self.A_input_mask,fw)
            pickle.dump(self.B_input_mask,fw)
            pickle.dump(cur_A,fw)
            pickle.dump(cur_B,fw)

        else:
            fr = open(load_dir,"rb")
            self.A_input = pickle.load(fr)
            self.B_input = pickle.load(fr)
            self.A_input_mask = pickle.load(fr)
            self.B_input_mask = pickle.load(fr)
            cur_A = pickle.load(fr)
            cur_B = pickle.load(fr)
            
        self.na = cur_A
        self.nb = cur_B
        
        self.train_num = min(cur_A,cur_B)
        print("68 benchmark face number: ",self.train_num)

        coord.request_stop()
        coord.join(threads)

    def average_gradients(self,tower_grads):
        average_grads = []
        for grad_and_vars in zip(*tower_grads):
            grads = []
            for g, _ in grad_and_vars:
                expend_g = tf.expand_dims(g, 0)
                grads.append(expend_g)
            grad = tf.concat(grads, 0)
            grad = tf.reduce_mean(grad, 0)
            v = grad_and_vars[0][1]
            grad_and_var = (grad, v)
            average_grads.append(grad_and_var)
        return average_grads
    
    def model_prediction_setup(self):
        
        
        self.input_A = tf.placeholder(tf.float32,[batch_size,img_height,img_width,img_layer],name="input_A")
        self.input_B = tf.placeholder(tf.float32,[batch_size,img_height,img_width,img_layer],name="input_B")
        
        with tf.variable_scope("Model") as scope:
            
            self.fake_B,self.fake_A = build_generator(self.input_A,self.input_B,name="generator")
        

    def model_setup(self):
        # self.input_A = tf.placeholder(tf.float32,[batch_size,img_height,img_width,img_layer],name="input_A")
        # self.input_B = tf.placeholder(tf.float32,[batch_size,img_height,img_width,img_layer],name="input_B")

        self.input_A_multigpu = tf.placeholder(tf.float32,[batch_size* gpu_num,img_height,img_width,img_layer],
                                               name="input_A")
        self.input_B_multigpu = tf.placeholder(tf.float32, [batch_size * gpu_num, img_height, img_width, img_layer],
                                               name="input_B")

        # self.input_A_mask = tf.placeholder(tf.bool,[3,img_height,img_width],name="input_A_mask")
        # self.input_B_mask = tf.placeholder(tf.bool,[3,img_height,img_width],name="input_B_mask")

        self.input_A_mask_multigpu = tf.placeholder(tf.bool,[gpu_num,3,img_height,img_width],name="input_A_mask")
        self.input_B_mask_multigpu = tf.placeholder(tf.bool, [gpu_num, 3, img_height, img_width], name="input_B_mask")



        self.fake_pool_A = tf.placeholder(tf.float32,[None,img_height,img_width,img_layer],name="fake_pool_A")
        self.fake_pool_B = tf.placeholder(tf.float32, [None, img_height, img_width, img_layer], name="fake_pool_B")

        self.num_fake_inputs = 0
        self.global_step = tf.Variable(0,name="global_step",trainable=False)
        self.lr = tf.placeholder(tf.float32,shape=[],name="lr")
        self.predictor = dlib.shape_predictor("/tmp2/chunting/makeup/beautyGAN-tf-Implement/preTrainedModel/shape_predictor_68_face_landmarks.dat")
        self.detector = dlib.get_frontal_face_detector()

        # using multi gpus
        g_grads = []
        d_A_grads = []
        d_B_grads = []
        optimizer = tf.train.AdamOptimizer(self.lr, beta1=0.5)
        with tf.variable_scope("Model") as scope:
            self.fake_As = []
            self.fake_Bs = []
            for gpu in range(gpu_num):
                with tf.device("/GPU:%d"%gpu):
                    with tf.name_scope("tower_%d"%gpu):
                        self.fake_B, self.fake_A = build_generator([self.input_A_multigpu[gpu]],
                                                                   [self.input_B_multigpu[gpu]], name="generator")
                        self.fake_As.append(self.fake_A)
                        self.fake_Bs.append(self.fake_B)
                        self.rec_A = generate_discriminator([self.input_A_multigpu[gpu]], "d_A")
                        self.rec_B = generate_discriminator([self.input_B_multigpu[gpu]], "d_B")
                        scope.reuse_variables()

                        self.fake_rec_A = generate_discriminator(self.fake_A, "d_A")
                        self.fake_rec_B = generate_discriminator(self.fake_B, "d_B")
                        
                        
                        self.cyc_B, self.cyc_A = build_generator(self.fake_A, self.fake_B, name="generator")

                        scope.reuse_variables()

                        self.fake_pool_rec_A = generate_discriminator([self.fake_pool_A[gpu]], "d_A")
                        self.fake_pool_rec_B = generate_discriminator([self.fake_pool_B[gpu]], "d_B")

                        self.perc_A = tf.cast(tf.image.resize_images((tf.expand_dims(self.input_A_multigpu[gpu],0) + 1) * 127.5, [224, 224]),
                                              tf.float32)
                        self.perc_B = tf.cast(tf.image.resize_images((tf.expand_dims(self.input_B_multigpu[gpu],0) + 1) * 127.5, [224, 224]),
                                              tf.float32)
                        self.perc_fake_B = tf.cast(tf.image.resize_images((self.fake_B + 1) * 127.5, [224, 224]),
                                                   tf.float32)
                        self.perc_fake_A = tf.cast(tf.image.resize_images((self.fake_A + 1) * 127.5, [224, 224]),
                                                   tf.float32)
                        self.perc = self.perc_loss_cal(
                            tf.concat([self.perc_A, self.perc_B, self.perc_fake_B, self.perc_fake_A], axis=0))
                        percep_norm, var = tf.nn.moments(self.perc, [1, 2], keep_dims=True)
                        self.perc = tf.divide(self.perc, tf.add(percep_norm, 1e-5))
                        scope.reuse_variables()

                        cyc_loss = tf.reduce_mean(tf.abs(self.input_A_multigpu[gpu,:,:,:] - self.cyc_A)) + tf.reduce_mean(
                            tf.abs(self.input_B_multigpu[gpu,:,:,:] - self.cyc_B))
                        disc_loss_A = tf.reduce_mean(tf.squared_difference(self.fake_rec_A, 1))
                        disc_loss_B = tf.reduce_mean(tf.squared_difference(self.fake_rec_B, 1))

                        print("gpu num is ",gpu)
                        temp_source = tf.cast((self.fake_B[0, :, :, 0] + 1) * 127.5, dtype=tf.float32)
                        temp_template = tf.cast((self.input_B_multigpu[gpu, :, :, 0] + 1) * 127.5, dtype=tf.float32)
                        
                        histogram_loss_r_lip = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][0],
                                                                       self.input_B_mask_multigpu[gpu][0])
                        histogram_loss_r_eye = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][1],
                                                                       self.input_B_mask_multigpu[gpu][1])
                        histogram_loss_r_face = self.histogram_loss_cal(temp_source, temp_template,self.input_A_mask_multigpu[gpu][2],
                                                                        self.input_B_mask_multigpu[gpu][2])
                        histogram_loss_r = histogram_loss_r_face + 0.1*histogram_loss_r_lip + histogram_loss_r_eye

                        temp_source = tf.cast((self.fake_B[0, :, :, 1] + 1) * 127.5, dtype=tf.float32)
                        temp_template = tf.cast((self.input_B_multigpu[gpu, :, :, 1] + 1) * 127.5, dtype=tf.float32)
                        histogram_loss_g_lip = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][0],
                                                                       self.input_B_mask_multigpu[gpu][0])
                        histogram_loss_g_eye = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][1],
                                                                       self.input_B_mask_multigpu[gpu][1])
                        histogram_loss_g_face = self.histogram_loss_cal(temp_source, temp_template,self.input_A_mask_multigpu[gpu][2],
                                                                        self.input_B_mask_multigpu[gpu][2])
                        histogram_loss_g = histogram_loss_g_lip + 0.1*histogram_loss_g_face + histogram_loss_g_eye

                        temp_source = tf.cast((self.fake_B[0, :, :, 2] + 1) * 127.5, dtype=tf.float32)
                        temp_template = tf.cast((self.input_B_multigpu[gpu, :, :, 2] + 1) * 127.5, dtype=tf.float32)
                        histogram_loss_b_lip = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][0],
                                                                       self.input_B_mask_multigpu[gpu][0])
                        histogram_loss_b_eye = self.histogram_loss_cal(temp_source, temp_template, self.input_A_mask_multigpu[gpu][1],
                                                                       self.input_B_mask_multigpu[gpu][1])
                        histogram_loss_b_face = self.histogram_loss_cal(temp_source, temp_template,self.input_A_mask_multigpu[gpu][2],
                                                                        self.input_B_mask_multigpu[gpu][2])
                        histogram_loss_b = histogram_loss_b_lip + 0.1*histogram_loss_b_face + histogram_loss_b_eye

                        makeup_loss = histogram_loss_r + histogram_loss_g + histogram_loss_b
                        # Using the same normalization as Gatys' neural style transfer
                        # Increase the lambda from 0.005 to 0.05
                        # cycle loss:2
                        perceptual_loss = tf.reduce_mean(
                            tf.squared_difference(self.perc[0], self.perc[2])) + tf.reduce_mean(
                            tf.squared_difference(self.perc[1], self.perc[3]))

                        g_loss = 2 * disc_loss_A + 2 * disc_loss_B + cyc_loss * 10  + makeup_loss + perceptual_loss * 0.05

                        d_loss_A = (tf.reduce_mean(tf.square(self.fake_pool_rec_A)) + tf.reduce_mean(
                            tf.squared_difference(self.rec_A, 1))) / 2.0
                        d_loss_B = (tf.reduce_mean(tf.square(self.fake_pool_rec_B)) + tf.reduce_mean(
                            tf.squared_difference(self.rec_B, 1))) / 2.0

                        self.model_vars = tf.trainable_variables()
                        d_A_vars = [var for var in self.model_vars if "d_A" in var.name]
                        d_B_vars = [var for var in self.model_vars if "d_B" in var.name]
                        g_vars = [var for var in self.model_vars if "generator" in var.name]
                        g_grad = optimizer.compute_gradients(g_loss,var_list=g_vars)
                        g_grads.append(g_grad)
                        d_A_grad = optimizer.compute_gradients(d_loss_A,var_list=d_A_vars)
                        d_A_grads.append(d_A_grad)
                        d_B_grad = optimizer.compute_gradients(d_loss_B,var_list=d_B_vars)
                        d_B_grads.append(d_B_grad)
                        
                        self.disc_A_loss_sum = tf.summary.scalar("disc_loss_A",disc_loss_A)
                        self.disc_B_loss_sum = tf.summary.scalar("disc_loss_B",disc_loss_B)
                        self.cyc_loss_sum = tf.summary.scalar("cyc_loss",cyc_loss)
                        self.makeup_loss_sum = tf.summary.scalar("makeup_loss",makeup_loss)
                        self.percep_loss_sum = tf.summary.scalar("perceptual_loss",perceptual_loss)
                        self.g_loss_sum = tf.summary.scalar("g_loss",g_loss)

                        self.g_summary = tf.summary.merge([
                            self.disc_A_loss_sum,self.disc_B_loss_sum,self.cyc_loss_sum,self.makeup_loss_sum,self.percep_loss_sum,self.g_loss_sum
                        ],"g_summary")

                        self.d_A_loss_sum = tf.summary.scalar("d_A_loss",d_loss_A)
                        self.d_B_loss_sum = tf.summary.scalar("d_B_loss",d_loss_B)
                        
                        self.sum_input_A = tf.summary.image('1_input_A', [(self.input_A_multigpu[gpu]+1)*127.5],  max_outputs=10)
                        self.sum_input_B = tf.summary.image('2_input_B', [(self.input_B_multigpu[gpu]+1)*127.5],  max_outputs=10)
                        self.sum_fake_A = tf.summary.image('3_fake_A', (self.fake_A+1)*127.5,  max_outputs=10)
                        self.sum_fake_B = tf.summary.image('4_fake_B', (self.fake_B+1)*127.5,  max_outputs=10)
#                         self.sum_mask_A = tf.summary.image('5_mask', (mask+1)*127.5,  max_outputs=10)
#                         self.sum_alpha_A = tf.summary.image('6_alpha', alpha,  max_outputs=10)
                        
                        self.sum_cyc_A = tf.summary.image('7_cyc_A', (self.cyc_A+1)*127.5,  max_outputs=10)
                        self.sum_cyc_B = tf.summary.image('8_cyc_B', (self.cyc_B+1)*127.5,  max_outputs=10)
                        
        g_grads = self.average_gradients(g_grads)
        self.g_trainer = optimizer.apply_gradients(g_grads)
        d_A_grads = self.average_gradients(d_A_grads)
        self.d_A_trainer = optimizer.apply_gradients(d_A_grads)
        d_B_grads = self.average_gradients(d_B_grads)
        self.d_B_trainer = optimizer.apply_gradients(d_B_grads)

        # using single gpu
        # with tf.variable_scope("Model") as scope:
        #     self.fake_B,self.fake_A = build_generator(self.input_A,self.input_B,name="generator")
        #     self.rec_A = generate_discriminator(self.input_A,"d_A")
        #     self.rec_B = generate_discriminator(self.input_B,"d_B")
        #
        #     scope.reuse_variables()
        #
        #     self.fake_rec_A = generate_discriminator(self.fake_A,"d_A")
        #     self.fake_rec_B = generate_discriminator(self.fake_B,"d_B")
        #     self.cyc_A,self.cyc_B = build_generator(self.fake_B,self.fake_A,name="generator")
        #
        #     scope.reuse_variables()
        #
        #     self.fake_pool_rec_A = generate_discriminator(self.fake_pool_A,"d_A")
        #     self.fake_pool_rec_B = generate_discriminator(self.fake_pool_B,"d_B")
        #
        #     self.perc_A = tf.cast(tf.image.resize_images((self.input_A+1)*127.5,[224,224]),tf.float32)
        #     self.perc_B = tf.cast(tf.image.resize_images((self.input_B+1)*127.5, [224, 224]), tf.float32)
        #     self.perc_fake_B = tf.cast(tf.image.resize_images((self.fake_B+1)*127.5, [224, 224]), tf.float32)
        #     self.perc_fake_A = tf.cast(tf.image.resize_images((self.fake_A+1)*127.5, [224, 224]), tf.float32)
        #     self.perc = self.perc_loss_cal(tf.concat([self.perc_A,self.perc_B,self.perc_fake_B,self.perc_fake_A],axis=0))
        #     percep_norm,var = tf.nn.moments(self.perc, [1, 2], keep_dims=True)
        #     self.perc = tf.divide(self.perc,tf.add(percep_norm,1e-5))


    def perc_loss_cal(self,input_tensor):
        vgg = vgg16.Vgg16("/tmp2/chunting/makeup/beautyGAN-tf-Implement/preTrainedModel/vgg16.npy")
        vgg.build(input_tensor)
        return vgg.conv4_1


    def mrf_loss_cal(self,source, template, ks):
        temp = tf.extract_image_patches(source, ksizes=[1, ks, ks, 1], strides=[1, 1, 1, 1], rates=[1, 1, 1, 1],
                                        padding="VALID")
        temp_shape = temp.get_shape().as_list()
        source_image_patch = tf.nn.l2_normalize(temp, dim=[3])

        template_image_patch = tf.extract_image_patches(template, ksizes=[1, ks, ks, 1], strides=[1, 1, 1, 1],
                                                        rates=[1, 1, 1, 1], padding="VALID")
        template_image_patch = tf.nn.l2_normalize(template_image_patch, dim=[3])

        shape = source_image_patch.get_shape().as_list()
        height = shape[1]
        width = shape[2]
        depth = shape[3]

        source_image_patch = tf.reshape(source_image_patch, [height * width, ks, ks, depth // ks // ks])
        template_image_patch = tf.reshape(template_image_patch, [height * width, ks, ks, depth // ks // ks])
        temp_reshape = tf.reshape(temp, [height * width, ks, ks, depth // ks // ks])

        template_image_patch = tf.transpose(template_image_patch, perm=[1, 2, 3, 0])
        convs = tf.nn.conv2d(source_image_patch, template_image_patch, strides=[1, 1, 1, 1], padding="VALID")
        argmax = tf.argmax(convs, dimension=3)

        best_match = tf.gather(temp_reshape, indices=argmax)
        best_match = tf.reshape(best_match, shape=temp_shape)

        loss = tf.divide(tf.reduce_mean(tf.squared_difference(best_match, temp)), ks ** 2)
        return loss


    def histogram_loss_cal(self,source,template,source_mask,template_mask):
        shape = tf.shape(source)
        source = tf.reshape(source, [1, -1])
        template = tf.reshape(template, [1, -1])
        source_mask = tf.reshape(source_mask,[-1, 256 * 256])
        template_mask = tf.reshape(template_mask,[-1,256*256])

        source = tf.boolean_mask(source, source_mask)
        template = tf.boolean_mask(template, template_mask)

        his_bins = 255

        max_value = tf.reduce_max([tf.reduce_max(source), tf.reduce_max(template)])
        min_value = tf.reduce_min([tf.reduce_min(source), tf.reduce_min(template)])

        hist_delta = (max_value - min_value) / his_bins
        hist_range = tf.range(min_value, max_value, hist_delta)
        hist_range = tf.add(hist_range, tf.divide(hist_delta, 2))

        s_hist = tf.histogram_fixed_width(source, [min_value, max_value], his_bins, dtype=tf.int32)
        t_hist = tf.histogram_fixed_width(template, [min_value, max_value], his_bins, dtype=tf.int32)

        s_quantiles = tf.cumsum(s_hist)
        s_last_element = tf.subtract(tf.size(s_quantiles), tf.constant(1))
        s_quantiles = tf.divide(s_quantiles, tf.gather(s_quantiles, s_last_element))

        t_quantiles = tf.cumsum(t_hist)
        t_last_element = tf.subtract(tf.size(t_quantiles), tf.constant(1))
        t_quantiles = tf.divide(t_quantiles, tf.gather(t_quantiles, t_last_element))

        nearest_indices = tf.map_fn(lambda x: tf.argmin(tf.abs(tf.subtract(t_quantiles, x))), s_quantiles,
                                    dtype=tf.int64)
        s_bin_index = tf.to_int64(tf.divide(source, hist_delta))
        s_bin_index = tf.clip_by_value(s_bin_index, 0, 254)

        matched_to_t = tf.gather(hist_range, tf.gather(nearest_indices, s_bin_index))
        # Using the same normalization as Gatys' style transfer: A huge variation--the normalization scalar is different according to different image
        # normalization includes variation constraints may be better
        matched_to_t = tf.subtract(tf.div(matched_to_t,127.5),1)
        source = tf.subtract(tf.divide(source,127.5),1)
        return tf.reduce_mean(tf.squared_difference(matched_to_t,source))


    def loss_cal(self):
        cyc_loss = tf.reduce_mean(tf.abs(self.input_A-self.cyc_A))+tf.reduce_mean(tf.abs(self.input_B-self.cyc_B))
        disc_loss_A = tf.reduce_mean(tf.squared_difference(self.fake_rec_A,1))
        disc_loss_B = tf.reduce_mean(tf.squared_difference(self.fake_rec_B,1))

        temp_source = tf.cast((self.fake_B[0,:,:,0]+1)*127.5,dtype=tf.float32)
        temp_template = tf.cast((self.input_B[0,:,:,0]+1)*127.5,dtype=tf.float32)
        histogram_loss_r_lip = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[0],self.input_B_mask[0])
        histogram_loss_r_eye = self.histogram_loss_cal(temp_source,temp_template, self.input_A_mask[1],self.input_B_mask[1])
        # histogram_loss_r_face = self.histogram_loss_cal(temp_source,temp_template, self.input_A_mask[2],self.input_B_mask[2])
        histogram_loss_r = histogram_loss_r_lip+histogram_loss_r_eye


        temp_source = tf.cast((self.fake_B[0,:,:,1]+1)*127.5,dtype=tf.float32)
        temp_template = tf.cast((self.input_B[0,:,:,1]+1)*127.5,dtype=tf.float32)
        histogram_loss_g_lip = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[0],self.input_B_mask[0])
        histogram_loss_g_eye = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[1],self.input_B_mask[1])
        # histogram_loss_g_face = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[2],self.input_B_mask[2])
        histogram_loss_g = histogram_loss_g_lip+histogram_loss_g_eye


        temp_source = tf.cast((self.fake_B[0,:,:,2]+1)*127.5,dtype=tf.float32)
        temp_template = tf.cast((self.input_B[0,:,:,2]+1)*127.5,dtype=tf.float32)
        histogram_loss_b_lip = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[0],self.input_B_mask[0])
        histogram_loss_b_eye = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[1],self.input_B_mask[1])
        # histogram_loss_b_face = self.histogram_loss_cal(temp_source,temp_template,self.input_A_mask[2],self.input_B_mask[2])
        histogram_loss_b = histogram_loss_b_lip+histogram_loss_b_eye

        makeup_loss = histogram_loss_r+histogram_loss_g+histogram_loss_b

        # Using the same normalization as Gatys' neural style transfer
        # Increase the lambda from 0.005 to 0.05
        # cycle loss:2
        perceptual_loss = tf.reduce_mean(tf.squared_difference(self.perc[0],self.perc[2]))+tf.reduce_mean(tf.squared_difference(self.perc[1],self.perc[3]))

        # tv_loss = tf.image.total_variation(self.fake_B)

        g_loss = cyc_loss*20+disc_loss_B+disc_loss_A+perceptual_loss*0.05+makeup_loss*0.5

        d_loss_A = (tf.reduce_mean(tf.square(self.fake_pool_rec_A))+tf.reduce_mean(tf.squared_difference(self.rec_A,1)))/2.0
        d_loss_B = (tf.reduce_mean(tf.square(self.fake_pool_rec_B)) + tf.reduce_mean(
            tf.squared_difference(self.rec_B, 1))) / 2.0

        optimizer = tf.train.AdamOptimizer(self.lr,beta1=0.5)

        self.model_vars = tf.trainable_variables()
        d_A_vars = [var for var in self.model_vars if "d_A" in var.name]
        d_B_vars = [var for var in self.model_vars if "d_B" in var.name]
        g_vars = [var for var in self.model_vars if "generator" in var.name]


        self.d_A_trainer = optimizer.minimize(d_loss_A,var_list=d_A_vars)
        self.d_B_trainer = optimizer.minimize(d_loss_B,var_list=d_B_vars)
        self.g_trainer = optimizer.minimize(g_loss,var_list=g_vars)

        for var in self.model_vars:
            print(var.name)

        self.disc_A_loss_sum = tf.summary.scalar("disc_loss_A",disc_loss_A)
        self.disc_B_loss_sum = tf.summary.scalar("disc_loss_B",disc_loss_B)
        self.cyc_loss_sum = tf.summary.scalar("cyc_loss",cyc_loss)
        self.makeup_loss_sum = tf.summary.scalar("makeup_loss",makeup_loss)
        self.percep_loss_sum = tf.summary.scalar("perceptual_loss",perceptual_loss)
        self.g_loss_sum = tf.summary.scalar("g_loss",g_loss)
         
        # self.tv_loss_sum = tf.summary.scalar("tv_loss",tv_loss)

        self.g_summary = tf.summary.merge([
            self.disc_A_loss_sum,self.disc_B_loss_sum,self.cyc_loss_sum,self.makeup_loss_sum,self.percep_loss_sum,self.g_loss_sum,
        ],"g_summary")

        self.d_A_loss_sum = tf.summary.scalar("d_A_loss",d_loss_A)
        self.d_B_loss_sum = tf.summary.scalar("d_B_loss",d_loss_B)
        
    
    
    def image_to_summary(self, sess, epoch, ptr_a, ptr_b):
                
        # self.tv_loss_sum = tf.summary.scalar("tv_loss",tv_loss)

        self.img_summary = tf.summary.merge([
            self.sum_input_A, self.sum_input_B, self.sum_fake_A, self.sum_fake_B, self.sum_cyc_A, self.sum_cyc_B],"img_summary")
        
        
       
        return sess.run(self.img_summary,feed_dict={
                self.input_A_multigpu:np.squeeze(self.A_input[ptr_a:ptr_a+gpu_num]),
                self.input_B_multigpu:np.squeeze(self.B_input[ptr_b:ptr_b+gpu_num])
         })
            

    def save_training_images(self,sess,epoch):
        if not os.path.exists("./output/imgs"):
            os.makedirs("./output/imgs")

        for i in range(0,10):
            fake_A_temp,fake_B_temp,cyc_A_temp,cyc_B_temp = sess.run([self.fake_A,self.fake_B,self.cyc_A,self.cyc_B],feed_dict={
                self.input_A:self.A_input[i],
                self.input_B:self.B_input[i]
            })
            imsave("./output/imgs/fakeA_"+str(epoch)+"_"+str(i)+".jpg",((fake_A_temp[0]+1)*127.5).astype(np.uint8))
            imsave("./output/imgs/fakeB_" + str(epoch) + "_" + str(i) + ".jpg",
                   ((fake_B_temp[0] + 1) * 127.5).astype(np.uint8))
            imsave("./output/imgs/cycA_" + str(epoch) + "_" + str(i) + ".jpg",
                   ((cyc_A_temp[0] + 1) * 127.5).astype(np.uint8))
            imsave("./output/imgs/cycB_" + str(epoch) + "_" + str(i) + ".jpg",
                   ((cyc_B_temp[0] + 1) * 127.5).astype(np.uint8))


    def fake_image_pool(self,num_fakes,fake,fake_pool):
        if num_fakes<pool_size:
            fake_pool[num_fakes] = fake
            return fake
        else:
            p = random.random()
            if p>0.5:
                random_id = random.randint(0,pool_size-1)
                temp = fake_pool[random_id]
                fake_pool[random_id] = fake
                return temp
            else:
                return fake


    def train_multigpu(self):
        

        init = [tf.local_variables_initializer(),tf.global_variables_initializer()]
        saver = tf.train.Saver()

        config = tf.ConfigProto(allow_soft_placement=True)
        with tf.Session(config=config) as sess:

            sess.run(init)
            self.input_read(sess)

            if to_restore:
                print("loading checkpoint")
                
           
                chkpt_fname = get_latest_model_checkpoint_path(check_dir, 'beautyGAN')
                saver.restore(sess,chkpt_fname)
                print('restore from ', chkpt_fname)

            writer = tf.summary.FileWriter("./output/ori")

            if not os.path.exists(check_dir):
                os.makedirs(check_dir)
            
            idx_a = np.arange(self.na)
            idx_b = np.arange(self.nb)
            
            for epoch in range(sess.run(self.global_step),900):
                print("in the epoch ",epoch)
                saver.save(sess,os.path.join(check_dir,"beautyGAN"),global_step=epoch)

                if epoch<100:
                    curr_lr = 0.0002
                else:
                    curr_lr = 0.0002-0.0002*(epoch-100)/800

                if save_training_images:
                    self.save_training_images(sess,epoch)
                    

                
                np.random.shuffle(idx_a)
                np.random.shuffle(idx_b)

                for ptr in range(0,self.train_num-(gpu_num-1),gpu_num):
                    
                    ptr_a = idx_a[ptr]
                    ptr_b = idx_b[ptr]
                    
                    
                    if (ptr_b+gpu_num) >= self.train_num:
                        continue
                                 
                    print("in the iteration",ptr)
                    print(ptr_b)
                    print(time.ctime())
                    _,fake_Bs_temp,fake_As_temp,summary_str = sess.run([self.g_trainer,self.fake_Bs,self.fake_As,self.g_summary],feed_dict={
                        self.input_A_multigpu:np.squeeze(self.A_input[ptr_a:ptr_a+gpu_num]),
                        self.input_B_multigpu:np.squeeze(self.B_input[ptr_b:ptr_b+gpu_num]),
                        self.lr:curr_lr,
                        self.input_A_mask_multigpu:self.A_input_mask[ptr_a:ptr_a+gpu_num],
                        self.input_B_mask_multigpu:self.B_input_mask[ptr_b:ptr_b+gpu_num],
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)

                    fake_A_temp = []
                    fake_B_temp = []
                    for i in range(gpu_num):
                        fake_A_temp.append(self.fake_image_pool(self.num_fake_inputs,fake_As_temp[i],self.fake_images_A))
                        fake_B_temp.append(self.fake_image_pool(self.num_fake_inputs,fake_Bs_temp[i],self.fake_images_B))

                    _,summary_str = sess.run([self.d_A_trainer,self.d_A_loss_sum],feed_dict={
                        self.input_A_multigpu:np.squeeze(self.A_input[ptr_a:ptr_a+gpu_num]),
                        self.input_B_multigpu:np.squeeze(self.B_input[ptr_b:ptr_b+gpu_num]),
                        self.lr:curr_lr,
                        self.fake_pool_A:np.squeeze(fake_A_temp)
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)

                    _,summary_str = sess.run([self.d_B_trainer,self.d_B_loss_sum],feed_dict={
                        self.input_A_multigpu: np.squeeze(self.A_input[ptr_a:ptr_a+gpu_num]),
                        self.input_B_multigpu: np.squeeze(self.B_input[ptr_b:ptr_b+gpu_num]),
                        self.lr: curr_lr,
                        self.fake_pool_B: np.squeeze(fake_B_temp)
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)
                    
                    if(ptr % 100 == 0):
                        img_summary = self.image_to_summary(sess, epoch, ptr_a, ptr_b)
                        
                        writer.add_summary(img_summary, epoch*self.train_num+ptr)
                       
                        
                    self.num_fake_inputs+=gpu_num
                sess.run(tf.assign(self.global_step,epoch+1))
            writer.add_graph(sess.graph)


    def train(self):

        self.loss_cal()
        with tf.Session() as sess:

            sess.run(init)
            self.input_read(sess)

            if to_restore:
                chkpt_fname = tf.train.latest_checkpoint(check_dir)
                saver.restore(sess,chkpt_fname)

            writer = tf.summary.FileWriter("./output/2")

            if not os.path.exists(check_dir):
                os.makedirs(check_dir)

            for epoch in range(sess.run(self.global_step),250):
                print("in the epoch ",epoch)
                saver.save(sess,os.path.join(check_dir,"beautyGAN"),global_step=epoch)

                if epoch<100:
                    curr_lr = 0.0002
                else:
                    curr_lr = 0.0002-0.0002*(epoch-100)/150

#                 if save_training_images:
#                     self.save_training_images(sess,epoch)

                idx_a = np.random.shuffle(np.arange(len(self.A_input)))
                idx_b = np.random.shuffle(np.arange(len(self.B_input)))

                for ptr in range(0,self.train_num):
        
                    
                    
                    ptr_a = idx_a[ptr]
                    ptr_b = idx_b[ptr]
                    print("in the iteration",ptr)
                    print(time.ctime())
                    _,fake_B_temp,fake_A_temp,summary_str = sess.run([self.g_trainer,self.fake_B,self.fake_A,self.g_summary],feed_dict={
                        self.input_A:self.A_input[ptr_a],
                        self.input_B:self.B_input[ptr_b],
                        self.lr:curr_lr,
                        self.input_A_mask:self.A_input_mask[ptr_a],
                        self.input_B_mask:self.B_input_mask[ptr_b],
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)

                    fake_A_temp1 = self.fake_image_pool(self.num_fake_inputs,fake_A_temp,self.fake_images_A)
                    fake_B_temp1 = self.fake_image_pool(self.num_fake_inputs,fake_B_temp,self.fake_images_B)

                    _,summary_str = sess.run([self.d_A_trainer,self.d_A_loss_sum],feed_dict={
                        self.input_A:self.A_input[ptr_a],
                        self.input_B:self.B_input[ptr_b],
                        self.lr:curr_lr,
                        self.fake_pool_A:fake_A_temp1
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)

                    _,summary_str = sess.run([self.d_B_trainer,self.d_B_loss_sum],feed_dict={
                        self.input_A: self.A_input[ptr],
                        self.input_B: self.B_input[ptr],
                        self.lr: curr_lr,
                        self.fake_pool_B: fake_B_temp1
                    })
                    writer.add_summary(summary_str,epoch*self.train_num+ptr)
                   
                        

                    self.num_fake_inputs+=1
                sess.run(tf.assign(self.global_step,epoch+1))
            writer.add_graph(sess.graph)

      
          
#     def test(self):
#         print("Testing the results")

#         config = tf.ConfigProto(allow_soft_placement=True)

#         with tf.Session(config=config) as sess:
#             sess.run(init)
#             self.input_read(sess)
#             chkpt_fanem = tf.train.latest_checkpoint(check_dir)
#             saver.restore(sess,chkpt_fanem)

#             if not os.path.exists("./output/imgs/test"):
#                 os.makedirs("./output/imgs/test")

#             for i in range(self.train_num):
# #                 # for multi gpu
# #                 fake_A_temp,fake_B_temp = sess.run([self.fake_As,self.fake_Bs],feed_dict={
# #                         self.input_A_multigpu:np.squeeze(self.A_input[i:i+gpu_num]),
# #                         self.input_B_multigpu:np.squeeze(self.B_input[i:i+gpu_num]),
# #                 })
# #                 imsave("./output/imgs/test/fakeA_" + str(i) + ".jpg",
# #                        ((fake_A_temp[0][0] + 1) * 127.5).astype(np.uint8))
# #                 imsave("./output/imgs/test/fakeB_" + str(i) + ".jpg",
# #                        ((fake_B_temp[0][0] + 1) * 127.5).astype(np.uint8))
#                 for single gpu
#                 fake_A_temp,fake_B_temp = sess.run([self.fake_A,self.fake_B],feed_dict={
#                     self.input_A:self.A_input[i],
#                     self.input_B:self.B_input[i]
#                 })
#                 imsave("./output/imgs/test/fakeA_" + str(i) + ".jpg",
#                        ((fake_A_temp[0] + 1) * 127.5).astype(np.uint8))
#                 imsave("./output/imgs/test/fakeB_" + str(i) + ".jpg",
#                        ((fake_B_temp[0] + 1) * 127.5).astype(np.uint8))
                
         


def main():
    model = BeautyGAN()
    if to_train:
        model.train_multigpu()
    elif to_test:
        model.test()

if __name__=="__main__":
    main()
