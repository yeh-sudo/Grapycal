import { DictTopic } from "objectsync-client"
import { AutoCompMenu } from "./autoCompMenu"
import { Editor } from "../../sobjects/editor"
import { Workspace } from "../../sobjects/workspace"
import { MouseOverDetector } from "../../component/mouseOverDetector"
import { GlobalEventDispatcher } from "../../component/eventDispatcher"
import { Vector2 } from "../../utils"

export class AddNodeMenu extends AutoCompMenu{
    private nodeTypesTopic:DictTopic<string,any>
    
    constructor(private editor:Editor){
        super()
        this.link(GlobalEventDispatcher.instance.onAnyKeyDown,this.onKeyDown)
        this.nodeTypesTopic = Workspace.instance.nodeTypesTopic
        this.link(this.nodeTypesTopic.onSet,this.updateNodeTypes)
        this.hideWhenClosed = true
    }

    private onKeyDown(e:KeyboardEvent){
        if(!MouseOverDetector.objectsUnderMouse.includes(this.editor)){
            return
        }
        if(document.activeElement==document.body && !this.opened && e.key.length == 1 && e.key.match(/[a-zA-Z0-9_]/) &&!e.ctrlKey && !e.altKey && !e.metaKey
        ){
            this.openAt(GlobalEventDispatcher.instance.mousePos.x,GlobalEventDispatcher.instance.mousePos.y)
            this.value = ''
        }
        if(e.key == 'Escape' && this.opened){
            this.close()
        }
        if(e.key == 'Backspace' && this.search.value.length == 0 && this.opened){
            this.close()
        }
    }

    protected updateNodeTypes(nodeTypes:Map<string,any>){
        let keys:string[] = []
        let values:string[] = []
        let options :{key:string,value:string,callback:()=>void,displayName:string}[] = []
        nodeTypes.forEach((nodeType,nodeTypeName)=>{
            nodeTypeName = nodeTypeName as string
            options.push({
                key:(nodeTypeName.toLowerCase().split('.')[1].slice(0,-4)), // remove Node suffix
                value:nodeTypeName,
                callback:()=>{
                    let translation = this.editor.transform.worldToLocal(GlobalEventDispatcher.instance.mousePos)
                    let snap = 17
                    let snapped = new Vector2(
                        Math.round(translation.x/snap)*snap,
                        Math.round(translation.y/snap)*snap
                    )
                    this.editor.createNode(nodeTypeName,{translation:snapped.toString()})
                },
                displayName:nodeTypeName.split('.')[1].slice(0,-4)
            })
        })
        this.setOptions(options)
    }
}
