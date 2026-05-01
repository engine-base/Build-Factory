// TODO: Build-Factory integration - port Onlook sandbox manager in a later phase.
export enum PreloadScriptState {
    LOADING = 'LOADING',
    LOADED = 'LOADED',
    INJECTED = 'INJECTED',
    ERROR = 'ERROR',
    UNLOADED = 'UNLOADED',
}

export type SandboxManager = Record<string, unknown>;
