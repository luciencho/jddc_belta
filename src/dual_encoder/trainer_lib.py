# coding:utf-8
from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function

import os
import numpy as np
import tensorflow as tf
import time
from annoy import AnnoyIndex

from src import utils


class Recorder(object):
    def __init__(self):
        self.lowest_loss = 10
        self.train_idx = 0
        self.dev_idx = 0
        self.train_losses = []
        self.dev_losses = []
        self.train_accs = []
        self.dev_accs = []

    def reset(self):
        self.train_losses = []
        self.dev_losses = []
        self.train_accs = []
        self.dev_accs = []

    def stats(self):
        train_loss = sum(self.train_losses) / len(self.train_losses)
        dev_loss = sum(self.dev_losses) / len(self.dev_losses)
        train_acc = sum(self.train_accs) / len(self.train_accs)
        dev_acc = sum(self.dev_accs) / len(self.dev_accs)
        self.reset()
        save = False
        if self.lowest_loss > dev_loss:
            save = True
            self.lowest_loss = dev_loss
        return {'train_loss': train_loss, 'dev_loss': dev_loss,
                'train_acc': train_acc, 'dev_acc': dev_acc, 'save': save}


def process(args):
    utils.make_directory(args.path['model'])
    tokenizer = args.tokenizer(args.path['vocab'])
    train_batch = args.batch(tokenizer, args.max_lens)
    train_batch.set_data(
        utils.read_lines(args.path['train_x']), utils.read_lines(args.path['train_y']))
    dev_batch = args.batch(tokenizer, args.max_lens)
    dev_batch.set_data(
        utils.read_lines(args.path['dev_x']), utils.read_lines(args.path['dev_y']))
    model = args.model(args)

    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_device
    config = tf.ConfigProto()
    config.gpu_options.per_process_gpu_memory_fraction = args.gpu_memory

    with tf.Session(config=config) as sess:
        sess.run(tf.global_variables_initializer())
        saver = tf.train.Saver(pad_step_number=True)
        recorder = Recorder()
        starter = time.time()

        for i in range(args.max_steps):
            input_x, input_y, idx, update_epoch = train_batch.next_batch(
                args.batch_size, recorder.train_idx)
            train_features = {'input_x_ph': input_x,
                              'input_y_ph': input_y, 'keep_prob_ph': args.keep_prob}
            recorder.train_idx = idx
            train_fetches, train_feed = model.train_step(train_features)
            _, train_loss, train_acc = sess.run(train_fetches, train_feed)
            recorder.train_losses.append(train_loss)
            recorder.train_accs.append(train_acc)

            if not i % args.show_steps and i:
                input_x, input_y, idx, update_epoch = dev_batch.next_batch(
                    args.batch_size, recorder.dev_idx)
                dev_features = {'input_x_ph': input_x,
                                'input_y_ph': input_y, 'keep_prob_ph': 1.0}
                recorder.dev_idx = idx
                dev_fetches, dev_feed = model.dev_step(dev_features)
                dev_loss, dev_acc = sess.run(dev_fetches, dev_feed)
                recorder.dev_losses.append(dev_loss)
                recorder.dev_accs.append(dev_acc)
                speed = args.show_steps / (time.time() - starter)
                utils.verbose(
                    r'        step {:05d} | train [{:.5f} {:.5f}] | '
                    r'dev [{:.5f} {:.5f}] | speed {:.5f} it/s'.format(
                        i, train_loss, train_acc, dev_loss, dev_acc, speed))
                starter = time.time()

            if not i % args.save_steps and i:
                features = recorder.stats()
                if features['save']:
                    saver.save(sess, args.path['model'])
                utils.verbose(
                    r'step {:05d} - {:05d} | train [{:.5f} {:.5f}] | '
                    r'dev [{:.5f} {:.5f}]'.format(
                        i - args.save_steps, i, features['train_loss'],
                        features['train_acc'], features['dev_loss'], features['dev_acc']))
                print('-+' * 55)
                utils.write_result(args, recorder.lowest_loss)

        utils.verbose('Start building vector space from dual encoder model')
        vectors = []
        infer_batch = args.batch(tokenizer, args.max_lens)
        infer_batch.set_data(utils.read_lines(args.path['train_x']),
                             utils.read_lines(args.path['train_y']))
        starter = time.time()
        idx = 0
        update_epoch = False
        i = 0
        while not update_epoch:
            input_x, input_y, idx, update_epoch = infer_batch.next_batch(
                args.batch_size, idx)
            infer_features = {'input_x_ph': input_x, 'keep_prob_ph': 1.0}
            infer_fetches, infer_feed = model.infer_step(infer_features)
            enc_questions = sess.run(infer_fetches, infer_feed)
            vectors += enc_questions
            if not i % args.show_steps and i:
                speed = args.show_steps / (time.time() - starter)
                utils.verbose('step : {:05d} | speed: {:.5f} it/s'.format(i, speed))
                starter = time.time()
            i += 1
    vectors = np.reshape(np.array(vectors), [-1, args.hidden])[: infer_batch.data_size]
    vec_dim = vectors.shape[-1]
    ann = AnnoyIndex(vec_dim)
    for n, ii in enumerate(vectors):
        ann.add_item(n, ii)
    ann.build(args.num_trees)
    ann.save(args.path['ann'])
    utils.verbose('Annoy has been dump in {}'.format(args.path['ann']))
