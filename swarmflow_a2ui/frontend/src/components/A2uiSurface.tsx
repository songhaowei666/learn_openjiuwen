import {A2uiSurface} from '@a2ui/react/v0_9';
import type {ReactComponentImplementation} from '@a2ui/react/v0_9';
import type {SurfaceModel} from '@a2ui/web_core/v0_9';

/** 渲染一个已经建好的 A2UI Surface。 */
export function A2uiSurfaceView({
  surface,
}: {
  surface: SurfaceModel<ReactComponentImplementation>;
}) {
  return (
    <section className="a2ui-panel">
      <A2uiSurface surface={surface} />
    </section>
  );
}
