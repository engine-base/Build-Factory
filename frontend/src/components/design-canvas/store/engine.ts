// TODO: Build-Factory integration - minimal stub of Onlook EditorEngine.
// The original engine wires ~20 manager modules (action, ast, branch, chat, code,
// copy, font, ide, image, insert, move, pages, sandbox, screenshot, snap, style,
// text, theme, etc.). Only the canvas/frames/overlay/element/state managers were
// extracted into Build-Factory. The remaining managers are stubbed as `any` here
// so that downstream UI code still type-checks; wire concrete implementations in a
// later phase.
import { makeAutoObservable } from 'mobx';
import { CanvasManager } from './canvas';
import { ElementsManager } from './element';
import { FramesManager } from './frames';
import { OverlayManager } from './overlay';
import { StateManager } from './state';

type StubManager = Record<string, any>;

const createStubManager = (): StubManager =>
    new Proxy(
        {},
        {
            get: (_t, prop) => {
                if (prop === 'then') return undefined;
                return (..._args: unknown[]) => undefined;
            },
        },
    );

export class EditorEngine {
    readonly canvas: CanvasManager;
    readonly elements: ElementsManager;
    readonly frames: FramesManager;
    readonly overlay: OverlayManager;
    readonly state: StateManager;

    readonly action: StubManager = createStubManager();
    readonly api: StubManager = createStubManager();
    readonly history: StubManager = createStubManager();
    readonly posthog: StubManager = createStubManager();
    readonly ast: StubManager = createStubManager();
    readonly branches: StubManager = createStubManager();
    readonly chat: StubManager = createStubManager();
    readonly code: StubManager = createStubManager();
    readonly copy: StubManager = createStubManager();
    readonly font: StubManager = createStubManager();
    readonly frameEvent: StubManager = createStubManager();
    readonly group: StubManager = createStubManager();
    readonly ide: StubManager = createStubManager();
    readonly image: StubManager = createStubManager();
    readonly insert: StubManager = createStubManager();
    readonly move: StubManager = createStubManager();
    readonly pages: StubManager = createStubManager();
    readonly sandbox: StubManager = createStubManager();
    readonly screenshot: StubManager = createStubManager();
    readonly snap: StubManager = createStubManager();
    readonly style: StubManager = createStubManager();
    readonly text: StubManager = createStubManager();
    readonly theme: StubManager = createStubManager();

    constructor(public readonly projectId: string) {
        this.canvas = new CanvasManager(this);
        this.elements = new ElementsManager(this);
        this.frames = new FramesManager(this);
        this.overlay = new OverlayManager(this);
        this.state = new StateManager();
        makeAutoObservable(this);
    }

    init() {}
    initBranches(_branches: unknown[]) {}
    clear() {}
    clearUI() {}
}
