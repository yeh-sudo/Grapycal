import importlib
import inspect
from typing import Dict

from grapycal.sobjects.node import Node
from objectsync import SObject
import logging
logger = logging.getLogger(__name__)

class Extension:
    @staticmethod
    def extension_exists(extension_name:str) -> bool:
        try:
            importlib.import_module(extension_name)
            return True
        except ModuleNotFoundError:
            return False
    def __init__(self,extension_name:str,existing_node_types:set[type[SObject]]=set()) -> None:
        if not self.extension_exists(extension_name):
            raise Exception(f'Extension {extension_name} not found')
        self.module = importlib.import_module(extension_name)
        self.extension_name = extension_name

        self.node_types:Dict[str,type[Node]] = {}
        self.node_types_without_extension_name:Dict[str,type[Node]] = {}
        for name, obj in inspect.getmembers(self.module):
            if inspect.isclass(obj) and issubclass(obj, Node):
                type_name = f'{self.extension_name}.{obj.__name__}'

                '''
                It may happen that the same node type is defined in multiple extensions. It is possible caused
                by diamond-imports. For example, grapycal_ext1 and grapycal_ext2 both import FunctionNode from 
                grapycal.sobjects.functionNode, and both mistakenly expose it in their __init__.py. This will
                cause an error when trying to register the node type to ObjectSync. To prevent this, we check
                if the node type already exists in the existing_node_types dict. If it does, we skip it.
                Not very elegant, but hope it works.
                '''
                if obj in existing_node_types:
                    logger.warning(f'Node type {type_name} already exists. Skipping')
                    continue

                self.node_types[type_name] = obj
                self.node_types_without_extension_name[obj.__name__] = obj

    def add_extension_name_to_node_type(self,node_type:str)->str:
        return f'{self.extension_name}.{node_type}'
