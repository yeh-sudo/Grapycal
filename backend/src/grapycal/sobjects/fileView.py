import os
from pathlib import Path
from urllib.parse import ParseResult, urlparse
from grapycal.extension.utils import list_to_dict
from grapycal.utils.httpResource import HttpResource
from objectsync import SObject, StringTopic
from grapycal.utils.io import read_workspace
import logging
logger = logging.getLogger(__name__)

class FileView(SObject):
    frontend_type = 'FileView'
    def build(self, name,**kwargs):
        super().build(**kwargs)
        self.name = self.add_attribute('name',StringTopic,name)
        
    def init(self):
        self.register_service('ls',self.ls)
        self.register_service('get_workspace_metadata',self.get_workspace_metadata)
        self.register_service('open_workspace',self.open_workspace)
        self.metadata_cache = {}

    def ls(self,path):
        raise NotImplementedError()

    def get_workspace_metadata(self,path):
        raise NotImplementedError()
    
    def open_workspace(self,path):
        self._server.globals.workspace._open_workspace_callback(path)

class LocalFileView(FileView):
    def ls(self,path):
        # root is cwd
        root = os.getcwd()
        path = path.replace('./','')
        path = os.path.join(root,path)
        if not os.path.exists(path):
            return []
        if os.path.isfile(path):
            return []
        result = []
        for f in os.listdir(path):
            if os.path.isdir(os.path.join(path,f)):
                if f.startswith('.'):
                    continue
                if f == '__pycache__':
                    continue
                result.append({'name':f,'type':'dir'})
            else:
                if f.endswith('.grapycal'):
                    result.append({'name':f,'path':f,'type':'workspace'})
        return result
    
    def get_workspace_metadata(self,path):
        if path in self.metadata_cache:
            return self.metadata_cache[path]
        version, metadata, _ = read_workspace(path,metadata_only=True)
        self.metadata_cache[path] = metadata
        return metadata
def path2str(path):
    return str(path).replace('\\','/')
class RemoteFileView(FileView):
    '''
    format:
    {
        "name": "workspaces",
        "files": [
            {
                "name": "Welcome.grapycal",
                "version": "0.9.0",
                "extensions": [
                    {
                        "name": "grapycal_builtin",
                        "version": "0.9.0"
                    }
                ]
            }
        ],
        "dirs": [
            {
                "name": "grapycal_torch",
                "files": [
                    {
                        "name": "ImageEdit.grapycal",
                        "version": "0.9.0",
                        "extensions": [
                            {
                                "name": "grapycal_torch",
                                "version": "0.1.2"
                            },
                            {
                                "name": "grapycal_builtin",
                                "version": "0.9.0"
                            }
                        ]
                    }
                ],
                "dirs": []
            }
        ]
    }
    '''
    def build(self, url:str, **kwargs):
        super().build(**kwargs)
        self.url = url
        self.metadata = HttpResource(f'{self.url}metadata.json',dict)
    
    async def ls(self,path):
        metadata = await self.metadata.get()
        if metadata is None:
            logger.error(f'Cannot get metadata from {self.url}')
            return []
        path = Path(path)

        dir = metadata
        subdirs = list_to_dict(dir['dirs'],'name')
        # find dir in metadata
        for p in path.parts:
            if p not in subdirs:
                return []
            dir = subdirs[p]

        result = []
        for f in dir['files']:
            if f['name'].endswith('.grapycal'):
                result.append({'type':'workspace','path':f['name']} | f)
        for d in dir['dirs']:
            result.append({'name':d['name'],'type':'dir','path':d['name']})
        return result
    
    async def get_workspace_metadata(self,path):
        metadata = await self.metadata.get()
        if metadata is None:
            return []
        path = Path(path)

        dir = metadata
        # find dir in metadata
        for p in path.parts[:-1]:
            subdirs = list_to_dict(dir['dirs'],'name')
            if p not in subdirs:
                return []
            dir = subdirs[p]

        file = list_to_dict(dir['files'],'name')[path.parts[-1]]

        return file
    
    async def open_workspace(self, path:str):
        # download workspace
        path = path.replace('./','')
        logger.info(f'Downloading workspace {path}')
        remote_file = await HttpResource(path2str(os.path.join(self.url,'files',path)),bytes).get()
        if remote_file is None:
            logger.error(f'Cannot get workspace from {self.url}')
            return
        
        local_path = os.getcwd().replace('\\','/')+'/'+path.replace('/','_')
        for i in range(100):
            import re
            # change name.grapycal to name_1.grapycal or name_1.grapycal to name_2.grapycal
            match = re.match(r'(.+/)(.+?)(_\d+)?(\.grapycal)',local_path)
            if match is None:
                raise Exception(f'Invalid path {local_path}')
            path, name, number, ext = match.groups()
            if i==0:
                prefix = self.name.get()+'_'
                # [a-zA-Z0-9_]
                prefix = re.sub(r'[^a-zA-Z0-9_]','',prefix)
                postfix = ''
            else:
                prefix = ''
                postfix = f'_{i}'
            local_path = f'{path}{prefix}{name}{postfix}{ext}'

            if not os.path.exists(local_path):
                break

        logger.info(f'Writing workspace {local_path}')
        with open(local_path,'wb') as f:
            f.write(remote_file)

        # open workspace
        
        self._server.globals.workspace._open_workspace_callback(local_path)