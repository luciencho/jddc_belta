# coding:utf-8
from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from annoy import AnnoyIndex

from src import utils
from src.retrieval.model import DualEncoderModel
from src.data_utils.vocab import Tokenizer
from src.data_utils.data import SoloBatch


class Searcher(object):
    def __init__(self, args):
        tokenizer = Tokenizer(args.path['vocab'])
        self.infer_batch = SoloBatch(tokenizer, [args.x_max_len, args.y_max_len])
        self.model = DualEncoderModel(args)
        self.ann = AnnoyIndex(args.emb_dim * 2)
        self.ann.load(args.path['ann'])
        self.sess = tf.Session()
        self.answers = utils.read_lines(args.path['train_y'])
        saver = tf.train.Saver()
        saver.restore(self.sess, args.model_path)

    def search_line(self, line, num=5):
        input_x = self.infer_batch.encode_line(line)
        infer_features = {'input_x_ph': input_x, 'keep_prob_ph': 1.0}
        infer_fetches, infer_feed = self.model.infer_step(infer_features)
        vector = self.sess.run(infer_fetches, infer_feed)[0]
        candidate_ids = self.ann.get_nns_by_vector(vector, num)
        return [self.answers[i] for i in candidate_ids]