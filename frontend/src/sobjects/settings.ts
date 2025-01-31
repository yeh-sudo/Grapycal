import { CompSObject } from "./compSObject"
import { Inspector } from "../inspector/inspector"
import { OptionsEditor } from "../inspector/OptionEditor"
import { bindTopicCookie } from "../utils"

export class Settings extends CompSObject{
    inspector: Inspector = new Inspector()

    protected onStart(): void {
        this.inspector.htmlItem.setParentElement(document.getElementById('tab-settings'))
        let editor = new OptionsEditor('theme',{'options':['light','simple','purple','fire','blocks']})
        this.inspector.addEditor(editor,'Appearance')
        bindTopicCookie(editor.topic,'theme','blocks')
        editor.topic.onSet.add((value)=>{
            // Seamless theme change
            let old = document.getElementById('custom-css')
            old.id = ''
            let swap: HTMLLinkElement = old.cloneNode(true) as HTMLLinkElement
            swap.id = 'custom-css'
            swap.setAttribute('href',`./css/${value}/main.css`)
            document.head.append(swap)
            setTimeout(() => {
                old.remove()
            }, 200);
        })
    }
}