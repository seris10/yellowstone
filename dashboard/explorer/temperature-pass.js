import {Pass} from './vendor/postprocessing/Pass.js';

// Draw temperature colors after bloom, retaining the terrain's depth buffer.
export class TemperaturePass extends Pass {
  constructor(scene,camera){super();this.scene=scene;this.camera=camera;this.needsSwap=false;}
  render(renderer,writeBuffer,readBuffer){
    const mask=this.camera.layers.mask,background=this.scene.background,autoClear=renderer.autoClear;
    this.camera.layers.set(1);this.scene.background=null;renderer.autoClear=false;
    try {renderer.setRenderTarget(readBuffer);renderer.render(this.scene,this.camera);}
    finally {this.camera.layers.mask=mask;this.scene.background=background;renderer.autoClear=autoClear;}
  }
}
