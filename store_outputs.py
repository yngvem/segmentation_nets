# Builtin imports
from pprint import pprint
import sys
from pathlib import Path
import argparse

# External imports
import json
import yaml
import sacred


def _load_file_using_module(path, module):
    if isinstance(path, str):
        path = Path(path)
    with path.open() as f:
        return module.load(f)


def load_json(path):
    return _load_file_using_module(path, json)


def load_yaml(path):
    return _load_file_using_module(path, yaml)


def parse_arguments():
    parser = argparse.ArgumentParser(
        formatter_class=SmartFormatter
    )
    parser.add_argument(
        "experiment",
        help="R|Path to folder with the JSON files specifying the parameters \n"
             "used in the experiment. The folder should contain the \n"
             "following files\n"
             "   - 'experiment_params.json'\n"
             "   - 'dataset_params.json'\n"
             "   - 'model_params.json'\n"
             "   - 'trainer_params.json'\n"
             "   - 'log_params.json'",
        type=str
    )
    parser.add_argument(
        "model_version",
        help="Suffix number to use for experiment name.",
        type=str
    )
    parser.add_argument(
        "eval_metric",
        help="The evaluation metric to use when finding the best architecture.",
        type=str
    )
    parser.add_argument(
        "output_file",
        help="The name of the h5 file that the outputs are saved to",
        type=str
    )

    args = parser.parse_args()
    return Path(args.experiment), args.model_version, args.eval_metric, args.output_file


class SmartFormatter(argparse.HelpFormatter):
    def _split_lines(self, text, width):
        if text.startswith('R|'):
            return text[2:].splitlines()
        return super()._split_lines(text, width)


if __name__ == '__main__':
    data_path, model_version, eval_metric, output_file = parse_arguments()

    dataset_params = load_json(data_path/'dataset_params.json')
    model_params = load_json(data_path/'model_params.json')
    trainer_params = load_json(data_path/'trainer_params.json')
    log_params = load_json(data_path/'log_params.json')
    experiment_params = load_json(data_path/'experiment_params.json')
    experiment_params['name'] += f'_{model_version}'
    print('Experiment_name')
    experiment_params['continue_old'] = True

    from scinets.utils.experiment import NetworkExperiment
    experiment = NetworkExperiment(
        experiment_params=experiment_params,
        model_params=model_params,
        dataset_params=dataset_params,
        trainer_params=trainer_params,
        log_params=log_params,
    )

    if not hasattr(experiment.evaluator, eval_metric):
        raise ValueError('The final evaluation metric must be a '
                            'parameter of the network evaluator.')
    best_it, (result, result_std) = experiment.find_best_model('val',
                                                                eval_metric)
    print(f'{" Final score ":=^80s}')
    print(f' Achieved a {eval_metric:s} of {result:.3f}, with a standard '
            f'deviation of {result_std:.3f}')
    print(f' This result was achieved at iteration {best_it}')
    print(80*"=")

    evaluation_results = experiment.evaluate_model('val', best_it)
    print(f'{" All evaluation metrics at best iteration ":=^80s}')
    print(f' Achieved a {eval_metric:s} of {result:.3f}, with a standard '
            f'deviation of {result_std:.3f}')
    print(80*"=")

    print(f'{" Saving input and output to disk ":=^80s}')
    experiment.save_outputs('val', 'val_input_output', best_it)
    print('Outputs saved')
