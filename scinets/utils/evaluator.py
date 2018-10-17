"""
TODO: BATCH NORM WILL NOW THINK WE ARE TRAINING IF WE WANT TO COMPUTE PERFORMANCE
      METRICS ON TRAINING SET!!!
"""
__author__ = 'Yngve Mardal Moe'
__email__ = 'yngve.m.moe@gmail.com'


import tensorflow as tf
import numpy as np


class ClassificationEvaluator:
    def __init__(self, network, scope='evaluator'):
        self.network = network
        self.input = network.input
        self.loss = network.loss
        self.out = network.out
        self.true_out = network.true_out

        self._out_channels = self.out.get_shape().as_list()[-1]

        with tf.variable_scope(scope):
            self.target = self._init_target()
            self.probabilities = self._init_probabilities()
            self.prediction = self._init_prediction()
            self.accuracy = self._init_accuracy()

    def _init_probabilities(self):
        if 'activation' in self.network.architecture[-1]:
            final_activation = self.network.architecture[-1]['activation']
            if (final_activation['operator'] == 'sigmoid'):
                return self.out

        with tf.variable_scope('probabilities'):
            return tf.nn.sigmoid(self.out)

    def _init_prediction(self):
        with tf.variable_scope('prediction'):
            return tf.cast(
                self.probabilities > 0.5,
                tf.float32,
                name='prediction'
            )

    def _init_target(self):
        with tf.variable_scope('target'):
            return tf.cast(self.network.true_out, tf.float32)

    def _init_accuracy(self):
        with tf.variable_scope('accuracy'):
            accuracy = tf.reduce_mean(
                tf.cast(
                    tf.equal(self.prediction, self.target),
                    tf.float32
                ),
                axis=tf.range(1, tf.rank(self.prediction))
            )
        return accuracy


class BinaryClassificationEvaluator(ClassificationEvaluator):
    def __init__(self, network, scope='evaluator'):
        super().__init__(network, scope)
        with tf.variable_scope(scope+'/'):
            self.num_elements = self._init_num_elements()
            self.true_positives = self._init_true_positives()
            self.true_negatives = self._init_true_negatives()
            self.false_positives = self._init_false_positives()
            self.false_negatives = self._init_false_negatives()

            self.precision = self._init_precision()
            self.recall = self._init_recall()
            self.dice = self._init_dice()

    def _init_num_elements(self):
        with tf.variable_scope('num_elements'):
            shape = self.out.get_shape().as_list()
            return np.prod(shape[1:])

    def _init_true_positives(self):
        with tf.variable_scope('true_positives'):
            true_positives = tf.count_nonzero(
                self.prediction * self.target,
                axis=tf.range(1, tf.rank(self.prediction)),
                dtype=tf.float32
            )
            return true_positives/self.num_elements

    def _init_true_negatives(self):
        with tf.variable_scope('true_negatives'):
            true_negatives =  tf.count_nonzero(
                (self.prediction - 1) * (self.target - 1),
                axis=tf.range(1, tf.rank(self.prediction)),
                dtype=tf.float32
            )
            return true_negatives/self.num_elements

    def _init_false_positives(self):
        with tf.variable_scope('fasle_positives'):
            false_positives = tf.count_nonzero(
                self.prediction * (self.target - 1),
                axis=tf.range(1, tf.rank(self.prediction)),
                dtype=tf.float32
            )
            return false_positives/self.num_elements

    def _init_false_negatives(self):
        with tf.variable_scope('false_negatives'):
            false_negatives = tf.count_nonzero(
                (self.prediction - 1) * self.target,
                axis=tf.range(1, tf.rank(self.prediction)),
                dtype=tf.float32
            )
            return false_negatives/self.num_elements

    def _init_precision(self):
        with tf.variable_scope('precision'):
            return self.true_positives / (self.true_positives + self.false_positives)

    def _init_recall(self):
        with tf.variable_scope('recall'):
            return self.true_positives / (self.true_positives + self.false_negatives)

    def _init_dice(self):
        with tf.variable_scope('dice'):
            dice = ((2*self.true_positives) 
                 / (2*self.true_positives + self.false_negatives
                    + self.false_positives))
        return dice


class NetworkTester:
    def __init__(self, metrics, dataset, evaluator, is_training, is_testing):
        self.metrics = metrics
        self.performance_ops = {metric: getattr(evaluator, metric)
                                       for metric in metrics}
        self.dataset, self.evaluator = dataset, evaluator
        self.is_training, self.is_testing = is_training, is_testing

    def get_numits(self, dataset):
        dataset = f'{dataset}_data_reader'
        dataset = getattr(self.dataset, dataset)
        data_len = len(dataset)
        batch_size = dataset.batch_size

        return int(np.ceil(data_len/batch_size))
    
    def get_feed_dict(self, dataset):
        if dataset == 'train':
            return {self.is_training: True}
        elif dataset == 'val':
            return {self.is_training: False, self.is_testing: False}
        elif dataset == 'test':
            return {self.is_training: False, self.is_testing: True}
        else:
            raise ValueError('`dataset` must be either `train`, `val` or `test`')

    @staticmethod
    def _join_performance_metric(performances, metric):
        return np.concatenate([batch[metric] for batch in performances], axis=0)

    def _compute_performances(self, performances, metric):
        performances = self._join_performance_metric(performances, metric)
        return performances.mean(), performances.std(ddof=1)

    def _create_performance_dict(self, performances):
        return {
            metric: self._compute_performances(performances, metric)
                for metric in performances[0]
        }

    def test_model(self, data_type, sess):
        """Compute the performance metrics using the specified evaluator.

        Arguments:
        ----------
        data_type : str
            Specifies which dataset to use, should be equal to `train`, 
            `val`, or `test`
        sess : tensorflow.Session
            The specified tensorflow session to use. All variables must be
            initialised beforehand.
        Returns:
        --------
        dict : 
            Dictionary specifying the average and standard deviation of all
            specified performance metrics. The keys are the metric names
            and the values are tuples where the first element is the mean
            and the second is the standard deviation.
        """
        feed_dict = self.get_feed_dict(data_type)
        num_its = self.get_numits(data_type)

        performances = []
        for i in range(num_its):
            performances.append(
                sess.run(self.performance_ops, feed_dict=feed_dict)
            )

        return self._create_performance_dict(performances)


if __name__ == '__main__':
    pass
