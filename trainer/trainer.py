import tensorflow as tf
import numpy as np
from . import optimizers
from pathlib import Path
from collections import Iterable
import json


class NetworkTrainer:
    """Class used to train a network instance.
    """
    def __init__(self, network, epoch_size, log_dir='./logs', 
                 train_op='AdamOptimizer', train_op_kwargs=None, 
                 max_checkpoints=10, save_step=100, verbose=True):
        """Trainer class for neural networks.

        Parameters
        ----------
        network : segmentation_nets.model.NeuralNet
            Network to train.
        train_op : str
            The name of the training operator to use, must be defined in
            `segmentation_nets.trainer.optimizers`.
        train_op_kwargs : dict (optional)
            Keyword arguments for the training operator, e.g. the learning_rate
            parameter will be set to 0.0001 ff this is set to
                {'learning_rate': 0.0001}
        max_checkpoints : int
            Maximum number of checkpoints to store.
        save_step : int
            How often to store checkpoints
        verbose : bool
            Whether additional printout should be produced.
        """
        self.network = network
        self.num_steps = 0
        self.epoch_size = epoch_size
        self.save_step = save_step

        self.train_op_name = train_op
        self.train_op_kwargs = {} if train_op_kwargs is None else train_op_kwargs

        self.log_dir = Path(log_dir)/network.name/'checkpoints'
        self.verbose = verbose

        with tf.variable_scope('trainer'):
            self._optimizer, self._train_step = self.init_train_op(
                train_op,
                train_op_kwargs
            )
            self._checkpoint_saver = self.init_saver(max_checkpoints)

    def train(self, session, num_steps, additional_ops=None):
        """Trains the network for a given number of steps.

        Parameters
        ----------
        session : tensorflow.Session
        num_steps : int
            Number of training steps to perform
        additional_ops : tensorflow.Operator
            Additional tensorflow operators to run.
        
        Returns
        -------
        list
            List of tuples containing the output of the operators in
            `additional_ops`.
        list
            List where the i-th element is the iteration number.
        """
        additional_ops = [] if additional_ops is None else additional_ops

        output = [None]*num_steps
        iterations = np.arange(self.num_steps, self.num_steps + num_steps + 1)
        for i in range(num_steps):
            output[i], _ = self.train_step(session, additional_ops=additional_ops)
        return output, iterations

    def train_step(self, session, additional_ops=None, feed_dict=None):
        """Performs one training step of the specified model.

        Parameters
        ----------
        session : tensorflow.Session
        additional_ops : list or tensorflow.Operator
            Additional tensorflow operators to run.
        feed_dict : dict
            The inputs to the network.
        
        Returns
        -------
        tuple
            Tuple containing the output of the operators in `additional_ops`.
        int
            Current iteration number.
        """
        additional_ops = [] if additional_ops is None else additional_ops
        try:
            iter(additional_ops)
            additional_ops = list(additional_ops)
        except TypeError:
            additional_ops = [additional_ops]
        
        run_list = [self._train_step] + additional_ops
        
        feed_dict = {} if feed_dict is None else feed_dict
        feed_dict = {
            self.network.is_training: True,
            **feed_dict
        }

        output = session.run(run_list, feed_dict=feed_dict)[1:]
        self.num_steps += 1
        if self.should_save:
            self.save_state(session)

        return output, self.num_steps

    def save_state(self, session):
        """Save a checkpoint of the model.
        """
        if self.verbose:
            print('Saving model')
        if not self.log_dir.is_dir():
            self.log_dir.mkdir(parents=True)
        file_name = str(self.log_dir/'checkpoint')
        self._checkpoint_saver.save(session, file_name,
                         global_step=self.num_steps)
        if self.verbose:
            print('Model saved')

    def load_state(self, session, step_num=None):
        """Load specified checkpoint, latest is used if `step_num` isn't given.
        """
        if step_num==None:
            with (self.log_dir/'latest_step.json') as f:
                step_num = json.load(f)
        if self.verbose:
            print('Loading model checkpoint {}'.format(step_num))
        log_file = str(self.log_dir/'checkpoint-{}'.format(step_num))
        self._checkpoint_saver.restore(session, log_file)
        self.num_steps = step_num
        if self.verbose:
            print('Model loaded')

    def init_saver(self, max_checkpoints):
        """Create an operator for saving and loading model state.
        """
        return tf.train.Saver(max_to_keep=max_checkpoints)

    def init_train_op(self, train_op, train_op_kwargs=None):
        """Set the operator used for weight updates.

        Parameters
        ----------
        train_op : str
            The optimizer to use for weight updates. Must be the name of an 
            element of the `optimizers.py` file.
        train_op_kwargs : dict (optional)
            The keyword arguments for the training operator
        
        Returns
        -------
        optimizer : tensorflow.Operator
            The optimizer operator
        train_step : tensorflow.Operator
            The train step operator, evaluating this perform one train step.
        """
        if self.network.loss is None:
            raise RuntimeError(
                'The network instance has no loss function.'
            )
        train_op_kwargs = {} if train_op_kwargs is None else train_op_kwargs

        Optimizer = getattr(optimizers, train_op)
        optimizer = Optimizer(**train_op_kwargs)

        UPDATE_OPS = tf.GraphKeys.UPDATE_OPS
        with tf.control_dependencies(tf.get_collection(UPDATE_OPS)):
            train_step = optimizer.minimize(self.network.loss)
        
        return optimizer, train_step

    @property
    def num_epochs(self):
        return self.num_steps//self.epoch_size

    @property
    def should_save(self):
        if self.save_step is None:
            return False
        return self.num_steps % self.save_step == 0
