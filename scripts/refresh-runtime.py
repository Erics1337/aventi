"""Recycle Lambda environments after secret sync without exposing their variables."""
import os
from uuid import uuid4

import boto3

client = boto3.client('lambda', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
project = os.environ.get('PROJECT', 'aventi')
environment = os.environ.get('ENV', 'dev')
revision = str(uuid4())
for role in ('api', 'worker', 'scheduler'):
    name = f'{project}-{environment}-{role}'
    client.get_waiter('function_updated_v2').wait(FunctionName=name)
    config = client.get_function_configuration(FunctionName=name)
    current_environment = config.get('Environment')
    if (not isinstance(current_environment, dict) or current_environment.get('Error')
            or not isinstance(current_environment.get('Variables'), dict)):
        raise RuntimeError(f'Cannot safely read Lambda environment for {name}; refresh aborted')
    variables = dict(current_environment['Variables'])
    variables['AVENTI_CONFIG_REVISION'] = revision
    client.update_function_configuration(FunctionName=name,
        RevisionId=config['RevisionId'], Environment={'Variables': variables})
    client.get_waiter('function_updated_v2').wait(FunctionName=name)
    print(f'Reloaded runtime configuration: {name}')
