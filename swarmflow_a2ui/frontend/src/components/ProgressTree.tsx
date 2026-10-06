import type {ReactComponentImplementation} from '@a2ui/react/v0_9';
import type {SurfaceModel} from '@a2ui/web_core/v0_9';
import {useMemo} from 'react';
import type {ProgressNode} from '../stores/progressStore';
import {useProgressStore} from '../stores/progressStore';
import {A2uiSurfaceView} from './A2uiSurface';

const STATUS_TEXT: Record<ProgressNode['status'], string> = {
  running: '进行中',
  completed: '已完成',
  waiting_for_human: '等待输入',
  failed: '失败',
};

/** 按 parentId 递归渲染进度树，human 节点下展开 A2UI。 */
export function ProgressTree({
  surfaces,
}: {
  surfaces: Map<string, SurfaceModel<ReactComponentImplementation>>;
}) {
  const nodes = useProgressStore((state) => state.nodes);
  const roots = useMemo(
    () => Object.values(nodes).filter((node) => node.parentId == null),
    [nodes],
  );
  if (roots.length === 0) {
    return <p className="empty-hint">提交问题后，这里会显示阶段、Agent 和人工节点。</p>;
  }
  return (
    <ul className="progress-tree">
      {roots.map((node) => (
        <TreeNode key={node.nodeId} node={node} nodes={nodes} surfaces={surfaces} />
      ))}
    </ul>
  );
}

function TreeNode({
  node,
  nodes,
  surfaces,
}: {
  node: ProgressNode;
  nodes: Record<string, ProgressNode>;
  surfaces: Map<string, SurfaceModel<ReactComponentImplementation>>;
}) {
  const children = Object.values(nodes).filter((item) => item.parentId === node.nodeId);
  const surface = node.surfaceId ? surfaces.get(node.surfaceId) : undefined;
  return (
    <li className={`progress-node status-${node.status}`}>
      <div className="progress-row">
        <span className={`status-dot status-${node.status}`} />
        <span className="node-type">{node.nodeType}</span>
        <span className="node-label">{node.label}</span>
        <span className="node-status">{STATUS_TEXT[node.status]}</span>
        {node.tokens != null && <span className="node-tokens">{node.tokens} tokens</span>}
      </div>
      {node.detail && <p className="node-detail">{node.detail}</p>}
      {surface && node.status === 'waiting_for_human' && <A2uiSurfaceView surface={surface} />}
      {children.length > 0 && (
        <ul>
          {children.map((child) => (
            <TreeNode key={child.nodeId} node={child} nodes={nodes} surfaces={surfaces} />
          ))}
        </ul>
      )}
    </li>
  );
}
