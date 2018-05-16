import tensorflow as tf
import sacred
from pathlib import Path
from ..model import model
from ..trainer import NetworkTrainer
from ..utils import TensorboardLogger
from ..utils import evaluator
from ..utils import HDFReader


class NetworkExperiment:
    def __init__(self, experiment_params, model_params, dataset_params, 
                 trainer_params, log_params):
        """
        experiment_parms={
            'log_dir': './',
            'name': 'test_experiment',
            'continue_old': False,
            'num_steps': 10000
        }

        model_params={
            'type': 'NeuralNet',
            'network_params: {
                'loss_function': 'sigmoid_cross_entropy_with_logits',
                'loss_kwargs': {},
                'architecture': [
                    {
                        'layer': 'conv2d',
                        'scope': 'conv1',
                        'out_size': 8,
                        'k_size': (5, 1),
                        'batch_norm': True,
                        'activation': 'relu',
                        'regularizer': {
                            'function': 'weight_decay',
                            'arguments': {
                                'amount': 0.5,
                                'name': 'weight_decay'
                            }
                        }
                    },
                    {
                        'layer': 'conv2d',
                        'scope': 'conv2',
                        'out_size': 16,
                        'k_size': 5,
                        'strides': 2,
                        'batch_norm': True,
                        'activation': 'relu',
                    },
                    {
                        'layer': 'conv2d',
                        'scope': 'conv3',
                        'out_size': 16,
                    }
                ]
                'verbose': True,
            }
        }

        log_params={
            'val_interval': 1000,
            'evaluator': BinaryClassificationEvaluator,
            'tb_params':
                {
                    'log_dict': None,
                    'train_log_dict': None,         (optional)
                    'val_log_dict': None,           (optional)
                    'train_collection': None,       (optional)
                    'val_collection': None          (optional)
                },
            'sacredboard_params':
                {
                    'log_dict': None,
                    'train_log_dict': None,         (optional)
                    'val_log_dict': None,           (optional)
                }
        }

        trainer_params={
            train_op: 'AdamOptimizer',
            train_op_kwargs: None,
            max_checkpoints: 10,
            save_step: 10,
            verbose: True
        }
        """
        # Set experiment properties
        self.log_dir = self._get_logdir(experiment_params)
        self.continue_old = self._get_continue_old(experiment_params)
        self.name = self._get_name(experiment_params)
        self.val_interval = log_params['val_log_frequency']
        
        # Create TensorFlow objects
        self.dataset, self.epoch_size = self._get_dataset(dataset_params)
        self.model = self._get_model(model_params)
        self.trainer = self._get_trainer(trainer_params)
        self.evaluator = self._get_evaluator(log_params['evaluator'])
        self.tb_logger = self._get_tensorboard_logger(log_params['tb_params'])

        self.train(experiment_params['num_steps'])
    
    def _get_continue_old(self, experiment_params):
        """Extract whether an old experiment should be continued.
        """
        if 'continue_old' in experiment_params:
            return experiment_params['continue_old']
        return False

    def _get_logdir(self, experiment_params):
        """Extract the log directory from the experiment parameters.
        """
        if 'log_dir' in experiment_params:
            return Path(experiment_params['log_dir'])
        return Path('./')

    def _get_name(self, experiment_params):
        """Enumerate the network name.
        """
        name = experiment_params['name']
        if self.continue_old:
            return name
        
        i = 0
        while self._name_taken(f'{name}_{i:02d}'):
            i += 1
        return f'{name}_{i:02d}'
    
    def _name_taken(self, name):
        """Checks if the given name is taken.
        """
        return (self.log_dir/name).is_dir()

    def _get_dataset(self, dataset_params):
        dataset = HDFReader(**dataset_params)
        epoch_size = len(dataset.train_data_reader)
        return dataset, epoch_size

    def _get_model(self, model_params):
        model_type = getattr(model, model_params['type'])
        return model_type(
            input_var=self.dataset.data,
            true_out=self.dataset.target,
            is_training=self.dataset.is_training,
            name=self.name,
            **model_params['network_params']
        )
    
    def _get_trainer(self, trainer_params):
        return NetworkTrainer(
            self.model,
            epoch_size=self.epoch_size,
            log_dir=self.log_dir,
            **trainer_params
        )

    def _get_evaluator(self, evaluator_type):
        evaluator_type = getattr(evaluator, evaluator_type)
        return evaluator_type(self.model)

    def _get_tensorboard_logger(self, tensorboard_params):
        return TensorboardLogger(
            self.evaluator,
            log_dir=self.log_dir,
            **tensorboard_params
        )

    def _init_session(self, sess):
        """Initialise the session. Must be run before any training iterations.
        """
        sess.run(tf.global_variables_initializer())
        if self.continue_old:
            self.trainer.load_state(sess)
        self.tb_logger.init_file_writers(sess)

    def _train_its(self, sess, *args, **kwargs):
        """Perform `self.val_interval` train steps and log validation metrics.
        """
        train_summaries, it_num = self.trainer.train(
            session=sess,
            num_steps=self.val_interval,
            additional_ops=[self.tb_logger.train_summary_op, self.model.loss]
        )
        train_summaries = [s[0] for s in train_summaries]
        self.tb_logger.log_multiple(train_summaries, it_num)

        val_summaries = sess.run(
            self.tb_logger.val_summary_op,
            feed_dict={self.model.is_training: False}
            )
        self.tb_logger.log(val_summaries, it_num[-1], log_type='val')

    def train(self, num_steps, *args, **kwargs):
        """Train the specified model for the given number of steps.
        """
        num_vals = num_steps//self.val_interval
        with tf.Session() as sess:
            self._init_session(sess)
            for i in range(num_vals):
                self._train_its(sess, *args, **kwargs)


class SacredExperiment(NetworkExperiment):
    def __init__(self, experiment_params, network_params, dataset_params, 
                 trainer_params, log_params):
        # Set experiment properties
        self.log_dir = self._get_logdir(experiment_params)
        self.continue_old = self._get_continue_old(experiment_params)
        self.name = self._get_name(experiment_params)
        self.val_interval = log_params['val_log_frequency']
        
        # Prepare for sacred:
        self.sacred_ex = sacred.Experiment(self.name, interactive=True)
        self.connect_to_database(experiment_params['database_params'])
        self.sacred_cfg = self.sacred_config(self.sacred_ex, experiment_params,
                                             network_params, dataset_params,
                                             trainer_params, log_params)
        self.main = self.sacred_main(self.sacred_ex)

    def connect_to_database(self, database_params):
        ex.observers.append(
            sacred.observers.MongoObserver.create(**database_params)
        )

    def sacred_cfg(self, experiment, experiment_params, network_params,
                   dataset_params, trainer_params, log_params):
        @experiment.config
        def cfg():
            experiment_params = experiment_params
            network_params = network_params
            dataset_params = dataset_params
            trainer_params = trainer_params
            log_params = log_params
            
    def sacred_main(self, experiment):
        @experiment.automain
        def main(_run, experiment_params, network_params, dataset_params,
                 trainer_params, log_params):
            self.dataset, self.epoch_size = self._get_dataset(dataset_params)
            self.model = self._get_model(model_params)
            self.trainer = self._get_trainer(trainer_params)
            self.evaluator = self._get_evaluator(log_params['evaluator'])
            self.tb_logger = self._get_tensorboard_logger(log_params['tb_params'])
            self.sacred_logger = self._get_sacred_logger(log_params['sacred_params'])

            self.train(experiment_params['train_steps'], _run)

    def _train_steps(self, sess):
        """Perform `self.val_interval` train steps.
        """
        train_ops = [self.tb_logger.train_summary_op,
                     self.sacred_logger.train_summary_op]

        summaries, it_nums = self.trainer.train(
            session=sess,
            num_steps=self.val_interval,
            additional_ops=train_ops
        )

        tb_summaries = [s[0] for s in summaries]
        sacred_summaries = [s[1] for s in summaries]
        return tb_summaries, sacred_summaries, it_nums

    def _val_logs(self, sess):
        """Create validation logs.
        """
        val_ops = [self.tb_logger.train_summary_op,
                   self.sacred_logger.train_summary_op]

        summaries = sess.run(
            val_ops,
            feed_dict={self.model.is_training: False}
            )

        tb_summaries, sacred_summaries = summaries
        return tb_summaries, sacred_summaries

    def _train_its(self, sess, _run, *args, **kwargs):
        """Perform `self.val_interval` train steps and log validation metrics.
        """

        tb_summaries, sacred_summaries, it_nums = self._train_steps(sess)
        self.tb_logger.log_multiple(tb_summaries, it_num)
        self.sacred_logger.log_multiple(sacred_summaries, run=_run)
        
        val_tb_summaries, val_sacred_summaries = self._val_logs(sess)
        self.tb_logger.log(val_summaries, it_num[-1], log_type='val', run=_run)
        self.sacred_logger.log(val_sacred_summaries, log_type='val', run=_run)

    def _get_sacred_logger(self, sacred_dict):
        return SacredLogger(self.evaluator, log_dir=self.log_dir, **sacred_dict)
