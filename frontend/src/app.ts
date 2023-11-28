import {ObjectSyncClient, SObject, StringTopic, DictTopic, IntTopic, SetTopic, FloatTopic, GenericTopic} from 'objectsync-client'

import { Node } from './sobjects/node'
import { Editor } from './sobjects/editor'
import { Root } from './sobjects/root'
import { expose } from './devUtils'
import { Port } from './sobjects/port'
import { Edge } from './sobjects/edge'
import { SoundManager } from './ui_utils/soundManager';
import { Sidebar } from './sobjects/sidebar'
import { WebcamStream, Workspace } from './sobjects/workspace'
import { ExtensionsSetting } from './ui_utils/extensionsSettings'
import { TextControl } from './sobjects/controls/textControl'
import { ButtonControl } from './sobjects/controls/buttonControl'
import { ImageControl } from './sobjects/controls/imageControl'
import { Footer } from './ui_utils/footer'
import { Header } from './ui_utils/header'
import { ThreeControl } from './sobjects/controls/threeControl'
import { LinePlotControl } from './sobjects/controls/linePlotControl'
import { Settings } from './ui_utils/settings'
import { FetchWithCache } from './utils'
import { FileView } from './sobjects/fileView'

export const soundManager = new SoundManager();

function tryReconnect(): void{
    // test websocket availability every 1 second
    const ws = new WebSocket(`ws://${location.hostname}:8765`);
    const to = setTimeout(() => {
        ws.close();
        tryReconnect();
    }, 1000);
    ws.onopen = () => {
        ws.close();
        clearTimeout(to);
        window.location.reload();
    };
}

let host = location.hostname;
const objectsync = new ObjectSyncClient(`ws://${host}:8765`,null,tryReconnect);

objectsync.register(Root);
objectsync.register(Workspace);
objectsync.register(Editor);
objectsync.register(Settings)
objectsync.register(FileView)
objectsync.register(Node);
objectsync.register(Port);
objectsync.register(Edge);
objectsync.register(Sidebar);

objectsync.register(TextControl)
objectsync.register(ButtonControl)
objectsync.register(ImageControl)
objectsync.register(ThreeControl)
objectsync.register(LinePlotControl)

objectsync.register(WebcamStream)

setTimeout(() => { // fix this
    new ExtensionsSetting(objectsync);
}, 200);


document.addEventListener('keydown', function(event) {
    if (event.ctrlKey && event.key === 'z' || event.metaKey && event.key === 'Z') {
        event.preventDefault();
        objectsync.undo(null);
    }
    if (event.ctrlKey && event.key === 'y' || event.metaKey && event.key === 'Y') {
        event.preventDefault();
        objectsync.redo(null);
    }
    if (event.ctrlKey && event.key === 's' || event.metaKey && event.key === 'S') {
        event.preventDefault();
        objectsync.emit('ctrl+s');
    }
    if (event.ctrlKey && event.key === 'q' || event.metaKey && event.key === 'Q') {
        event.preventDefault();
        objectsync.makeRequest('exit');
        //reload page
        setTimeout(() => {
            
            window.location.reload();
        }, 1000);
    }
    if (event.key === 'Tab') {
        event.preventDefault();
        let sidebarRight = document.getElementById('sidebar-collapse-right').parentElement;
        if (sidebarRight.classList.contains('collapsed')) {
            sidebarRight.classList.remove('collapsed');
            // sidebarLeft.classList.remove('collapsed');
        } else {
            sidebarRight.classList.add('collapsed');
            // sidebarLeft.classList.add('collapsed');
        }
    }
});

document.addEventListener('contextmenu', function(event) {
    event.preventDefault();
});

function documentReady(callback: Function): void {
    if (document.readyState === "complete" || document.readyState === "interactive") 
        callback()
    else
        document.addEventListener("DOMContentLoaded", (event: Event) => {
            callback()
        })

  }

documentReady(function(event: Event) {
    document.getElementById('sidebar-collapse-right').addEventListener('click', function(event) {
        let sidebar = document.getElementById('sidebar-collapse-right').parentElement;
        if (sidebar.classList.contains('collapsed')) {
            sidebar.classList.remove('collapsed');
            document.getElementById('sidebar-collapse-right').innerText = '>'
        } else {
            sidebar.classList.add('collapsed');
            document.getElementById('sidebar-collapse-right').innerText = '<'
        }
    });  
    
    // new Header()
    new Footer()
})



expose('o',objectsync)

let fetchWithCache = new FetchWithCache().fetch

export {fetchWithCache}