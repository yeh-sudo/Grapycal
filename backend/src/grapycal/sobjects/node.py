from abc import ABCMeta
import io
from itertools import count
import logging
import random
from grapycal.sobjects.controls.buttonControl import ButtonControl
from grapycal.sobjects.controls.imageControl import ImageControl
from grapycal.sobjects.controls.linePlotControl import LinePlotControl

from grapycal.sobjects.controls.textControl import TextControl
logger = logging.getLogger(__name__)
from contextlib import contextmanager
import functools
import traceback
from typing import TYPE_CHECKING, Any, Callable, Generator, TypeVar
from grapycal.extension.utils import NodeInfo
from grapycal.sobjects.controls.control import Control
from grapycal.sobjects.edge import Edge
from grapycal.sobjects.port import InputPort, OutputPort
from grapycal.utils.io import OutputStream
from objectsync import SObject, StringTopic, IntTopic, ListTopic, ObjListTopic, FloatTopic, Topic, ObjDictTopic, SetTopic
from objectsync.sobject import SObjectSerialized, WrappedTopic

if TYPE_CHECKING:
    from grapycal.core.workspace import Workspace
    
class NodeMeta(ABCMeta):
    class_def_counter = count()
    def_order = {}
    def __init__(self, name, bases, attrs):
        self.def_order[name] = next(self.class_def_counter)
        return super().__init__(name, bases, attrs)

class Node(SObject,metaclass=NodeMeta):
    frontend_type = 'Node'
    category = 'hidden'

    @classmethod
    def get_def_order(cls):
        return cls.def_order[cls.__name__]

    def build(self,is_preview=False,translation='0,0',restore_info=None,**build_node_args):
        
        self.shape = self.add_attribute('shape', StringTopic, 'normal') # normal, simple, round
        self.output = self.add_attribute('output', ListTopic, [], is_stateful=False)
        self.label = self.add_attribute('label', StringTopic, '', is_stateful=False)
        self.label_offset = self.add_attribute('label_offset', FloatTopic, 0)
        self.translation = self.add_attribute('translation', StringTopic,translation)
        self.is_preview = self.add_attribute('is_preview', IntTopic, 1 if is_preview else 0)
        self.category_ = self.add_attribute('category', StringTopic, self.category)
        self.exposed_attributes = self.add_attribute('exposed_attributes', ListTopic, [])
        self.running = self.add_attribute('running',IntTopic,1,is_stateful=False) # 0 for running, other for not running
        self.css_classes = self.add_attribute('css_classes',SetTopic,[])
        self.icon_path = self.add_attribute('icon_path',StringTopic,f'{self.__class__.__name__[:-4].lower()}',is_stateful=False)

        # for inspector
        self.type_topic = self.add_attribute('type', StringTopic, self.get_type_name())

        self.in_ports = self.add_attribute('in_ports', ObjListTopic[InputPort])
        self.out_ports = self.add_attribute('out_ports', ObjListTopic[OutputPort])

        self.controls = self.add_attribute('controls', ObjDictTopic[Control])

        '''
        Let user override build_node method instead of build method so that they don't have to call super().build(args) in their build method.
        '''
        if restore_info is not None:
            self.old_version, self.old_node_info = restore_info

        self.build_node(**build_node_args)

    def build_node(self):
        '''
        Create attributes, ports, and controls here.
        
        Note: 
            This method will not be called when the object is being restored. The child objects will be restored automatically instead of
        running this method again.
        '''

    def init(self):

        self.workspace:Workspace = self._server.globals.workspace
        
        from grapycal.sobjects.editor import Editor # import here to avoid circular import
        parent = self.get_parent()
        if isinstance(parent, Editor):
            self.editor = parent
        else:
            self.editor = None

        self.on('double_click', self.double_click, is_stateful=False)
        self.on('spawn', self.spawn , is_stateful=False)

        
        self._output_stream = OutputStream(self.raw_print)
        self._output_stream.set_event_loop(self.workspace.get_communication_event_loop())
        self.workspace.get_communication_event_loop().create_task(self._output_stream.run())

        self.init_node()

        if hasattr(self,'old_version'):
            self.restore_from_version(self.old_version,self.old_node_info)

    def init_node(self):
        '''
        This method is called after the node is built and its ports and controls are created. Use this method if you want to do something after
        the node is built.
        '''
        pass

    def restore_from_version(self,version:str,old:NodeInfo):
        '''
        Called when the node is created as a result of a old node being upgraded.
        The old node's information (including attribute values) is in the `old` argument.
        '''
        self.restore_attributes('translation')

    def restore_attributes(self,*attribute_names:str|tuple[str,str]):
        '''
        Recover attributes from the old node.
        '''
        assert self.old_node_info is not None
        for name in attribute_names:
            if isinstance(name,tuple):
                old_name,new_name = name
            else:
                old_name,new_name = name,name
            if not self.has_attribute(new_name):
                logger.warning(f'Attribute {new_name} does not exist in {self}')
                continue
            if not self.old_node_info.has_attribute(old_name):
                logger.warning(f'Attribute {old_name} does not exist in the old node of {self}')
                continue
            new_attr = self.get_attribute(new_name)
            old_attr = self.old_node_info[old_name]
            if isinstance(new_attr,WrappedTopic):
                new_attr.set_raw(old_attr)
            else:
                new_attr.set(old_attr)

    def restore_controls(self,*control_names:str|tuple[str,str]):
        '''
        Recover controls from the old node.
        '''
        assert self.old_node_info is not None
        for name in control_names:
            if isinstance(name,tuple):
                old_name,new_name = name
            else:
                old_name,new_name = name,name
            if not (new_name in self.controls):
                logger.warning(f'Control {new_name} does not exist in {self}')
                continue
            if not (old_name in self.old_node_info.controls):
                logger.warning(f'Control {old_name} does not exist in the old node of {self}')
                continue
            self.controls[new_name].restore_from(self.old_node_info.controls[old_name])

    def spawn(self, client_id):
        '''
        Called when a client wants to spawn a node.
        '''
        new_node = self.workspace.get_workspace_object().main_editor.create_node(type(self))
        new_node.add_tag(f'spawned_by_{client_id}') # So the client can find the node it spawned and make it follow the mouse
        logger.info(f'Created a new {type(self).__name__}')

    def destroy(self) -> SObjectSerialized:
        '''
        Called when the node is destroyed. You can override this method to do something before the node is destroyed.
        Note: Overrided methods should call return super().destroy() at the end.
        '''
        self._output_stream.close()
        # remove all edges connected to the ports
        for port in self.in_ports:
            for edge in port.edges[:]:
                edge.remove()
        for port in self.out_ports:
            for edge in port.edges[:]:
                edge.remove()
        return super().destroy()

    def add_in_port(self,name:str,max_edges=64,display_name=None):
        '''
        Add an input port to the node.
        '''
        port = self.add_child(InputPort,name=name,max_edges=max_edges,display_name=display_name)
        self.in_ports.insert(port)
        return port

    def add_out_port(self,name:str,max_edges=64,display_name=None):
        '''
        Add an output port to the node.
        '''
        port = self.add_child(OutputPort,name=name,max_edges=max_edges,display_name=display_name)
        self.out_ports.insert(port)
        return port
    
    def remove_in_port(self,name:str):
        '''
        Remove an input port from the node.
        '''
        #find the port with the given name
        for port in self.in_ports:
            assert port is not None
            if port.name.get() == name:
                break
        else:
            raise ValueError(f'Port with name {name} does not exist')
        
        #remove all edges connected to the port
        for edge in port.edges[:]: 
            edge.remove() # do this in port.remove()?   

        #remove the port
        self.in_ports.remove(port)
        port.remove()

    def remove_out_port(self,name:str):
        '''
        Remove an output port from the node.
        '''
        #find the port with the given name
        for port in self.out_ports:
            assert port is not None
            if port.name.get() == name:
                break
        else:
            raise ValueError(f'Port with name {name} does not exist')
        
        #remove all edges connected to the port
        for edge in port.edges[:]: 
            edge.remove() # do this in port.remove()?

        #remove the port
        self.out_ports.remove(port)
        port.remove()

    def get_in_port(self,name:str) -> InputPort:
        '''
        Get an input port by its name.
        '''
        for port in self.in_ports:
            assert port is not None
            if port.name.get() == name:
                return port
        raise ValueError(f'Port with name {name} does not exist')
    
    def get_out_port(self,name:str) -> OutputPort:
        '''
        an output port by its name.
        '''
        for port in self.out_ports:
            assert port is not None
            if port.name.get() == name:
                return port
        raise ValueError(f'Port with name {name} does not exist')
    
    def has_in_port(self,name:str) -> bool:
        '''
        Check if an input port exists.
        '''
        for port in self.in_ports:
            assert port is not None
            if port.name.get() == name:
                return True
        return False
    
    def has_out_port(self,name:str) -> bool:
        '''
        Check if an output port exists.
        '''
        for port in self.out_ports:
            assert port is not None
            if port.name.get() == name:
                return True
        return False
    
    T = TypeVar('T', bound=Control)
    def add_control(self,control_type:type[T],name:str|None=None,**kwargs) -> T:
        '''
        Add a control to the node.
        '''
        if name is not None:
            if name in self.controls:
                raise ValueError(f'Control with name {name} already exists')
        else:
            name = 'Control0'
            i=0
            while name in self.controls:
                i+=1
                name = f'Control{i}'

        control = self.add_child(control_type,**kwargs)
        self.controls.add(name,control)
        return control
    
    def add_text_control(self,text:str='', label:str='',readonly=False, editable:bool=True,name:str|None=None) -> TextControl:
        '''
        Add a text control to the node.
        '''
        control = self.add_control(TextControl,text=text,label=label,readonly=readonly,editable=editable,name=name)
        return control
    
    def add_button_control(self,label:str='',name:str|None=None) -> ButtonControl:
        '''
        Add a button control to the node.
        '''
        control = self.add_control(ButtonControl,label=label,name=name)
        return control
    
    def add_image_control(self,name:str|None=None) -> ImageControl:
        '''
        Add an image control to the node.
        '''
        control = self.add_control(ImageControl,name=name)
        return control
    
    def add_lineplot_control(self,name:str|None=None) -> LinePlotControl:
        '''
        Add a line plot control to the node.
        '''
        control = self.add_control(LinePlotControl,name=name)
        return control

    def remove_control(self,control:str|Control):
        if isinstance(control,str):
            control = self.controls[control]
        self.controls.remove(control)
        control.remove()
    
    # Wrap the SObject.addattribute() to make shorthand of exposing attributes after adding them.
    T1 = TypeVar("T1", bound=Topic|WrappedTopic)
    def add_attribute(
        self, topic_name:str, topic_type: type[T1], init_value=None, is_stateful=True,
        editor_type:str|None=None, display_name:str|None=None, order_strict:bool|None=None, **editor_args
        ) -> T1: 
        '''
        If order_strict is None, it will be set to the ame as is_stateful.
        The usage of editor_type and editor_args is the same as the expose_attribute method.
        '''

        if order_strict is None:
            order_strict = is_stateful
        
        attribute = super().add_attribute(topic_name, topic_type, init_value, is_stateful,order_strict=order_strict)
        if editor_type is not None:
            self.expose_attribute(attribute,editor_type,display_name,**editor_args)
        return attribute
    
    def expose_attribute(self,attribute:Topic|WrappedTopic,editor_type,display_name=None,**editor_args):
        '''
        Expose an attribute to the editor.
        Args:
            - attribute: The attribute to expose.

            - editor_type: The type of the editor to use. Can be ``text`` or ``list``.

        List of editor types:
            - ``dict``: A dictionary editor. Goes with a DictTopic. editor_args: {
                'key_options':list[str]|None,
                'value_options':list[str]|None,
                'key_strict':bool|None,
                'value_strict':bool|None,
            }

            - ``list``: A list editor. Goes with a ListTopic. editor_args: {}

            - ``options``: A dropdown editor. Goes with a StringTopic. editor_args: {
                'options':list[str],
            }

            - ``text``: A text editor. Goes with a StringTopic. 

            - ``int``: An integer editor. Goes with an IntTopic. editor_args: {}

            - ``float``: A float editor. Goes with a FloatTopic. editor_args: {}
            
            

            

        '''
        if editor_args is None:
            editor_args = {}
        name = attribute.get_name()
        if display_name is None:
            display_name = name.split('/')[-1]
        editor_args['type'] = editor_type
        self.exposed_attributes.insert({
            'name':name,
            'display_name':display_name,
            'editor_args':editor_args
        })

    def print(self,*args,**kwargs):
        '''
        Print to the node's output.
        '''
        # print(*args,**kwargs,file=self._output_stream)
        # self._output_stream.flush()

        # maybe the self._output_stream can be abandoned
        output = io.StringIO()
        print(*args, file=output, **kwargs)
        contents = output.getvalue()
        output.close()

        self.raw_print(contents)

    def raw_print(self,data):
        if data=='':
            return
        if self.is_destroyed():
            logger.debug(f'Output received from a destroyed node {self.get_id()}: {data}')
        else:
            if len(self.output) > 100:
                self.output.set([])
                self.output.insert(['error','Too many output lines. Cleared.'])
            self.output.insert(['output',data])


    '''
    Run tasks in the background or foreground, redirecting stdout to the node's output stream.
    '''

    @contextmanager
    def _redirect_output(self):
        '''
        Returns a context manager that redirects stdout to the node's output stream.
        '''

        try:
            self._output_stream.enable_flush()
            with self.workspace.redirect(self._output_stream):
                yield
        finally:
            self._output_stream.disable_flush()

    def _run_in_background(self,task:Callable[[],None],to_queue=True,redirect_output=False):
        '''
        Run a task in the background thread.
        '''

        def wrapped():
            self.running.set(0)
            self.workspace.background_runner.set_exception_callback(lambda e:self._on_exception(e,truncate=3))
            if redirect_output:
                with self._redirect_output():
                    ret = task()
            else:
                ret = task()
            self.running.set(random.randint(0,10000))
            return ret
        
        self.workspace.background_runner.push(wrapped,to_queue=to_queue)
        
    def _run_directly(self,task:Callable[[],None],redirect_output=False):
        '''
        Run a task in the current thread.
        '''
        self.running.set(0)
        try:
            if redirect_output:
                with self._redirect_output():
                    task()
            else:
                task()
        except Exception as e:
            self._on_exception(e,truncate=1)
        self.running.set(random.randint(0,10000))

    def run(self,task:Callable,background=True,to_queue=True,redirect_output=False,*args,**kwargs):
        '''
        Run a task in the node's context i.e. the stdout and errors will be redirected to the node's output attribute and be displayed in front-end.

        Args:
            - task: The task to run.

            - background: If set to True, the task will be scheduled to run in the background thread. Otherwise, it will be run in the current thread immediately.
            
            - to_queue: This argument is used only when `background` is True. If set to True, the task will be pushed to the :class:`.BackgroundRunner`'s queue.\
            If set to False, the task will be pushed to its stack. See :class:`.BackgroundRunner` for more details.
        '''
        task = functools.partial(task,*args,**kwargs)
        if background:
            self._run_in_background(task,to_queue,redirect_output=False)
        else:
            self._run_directly(task,redirect_output=False)

    def _on_exception(self, e, truncate=0):
        message = ''.join(traceback.format_exception(e)[truncate:])
        if self.is_destroyed():
            logger.warning(f'Exception occured in a destroyed node {self.get_id()}: {message}')
        else:
            self.running.set(random.randint(0,10000))
            if len(self.output) > 100:
                self.output.set([])
                self.output.insert(['error','Too many output lines. Cleared.'])
            self.output.insert(['error',message])


    def flash_running_indicator(self):
        self.running.set(0)
        self.running.set(random.randint(0,10000))

    '''
    Node events
    '''
    
    def edge_activated(self, edge:Edge, port:InputPort):
        '''
        Called when an edge on an input port is activated.
        '''
        pass

    def input_edge_added(self, edge:Edge, port:InputPort):
        '''
        Called when an edge is added to an input port.
        '''
        pass

    def input_edge_removed(self, edge:Edge, port:InputPort):
        '''
        Called when an edge is removed from an input port.
        '''
        pass

    def output_edge_added(self, edge:Edge, port:OutputPort):
        '''
        Called when an edge is added to an output port.
        '''
        pass

    def output_edge_removed(self, edge:Edge, port:OutputPort):
        '''
        Called when an edge is removed from an output port.
        '''
        pass

    def double_click(self):
        '''
        Called when the node is double clicked by an user.
        '''
        pass