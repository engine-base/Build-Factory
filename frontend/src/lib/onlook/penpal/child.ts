// TODO: Build-Factory integration - removed Onlook dependency (@onlook/web-preload)
// Loose typing: child methods are dispatched dynamically; concrete shape lives in the iframe preload script.
type PenpalChildMethodsType = Record<string, (...args: unknown[]) => unknown>;

// Preload methods should be treated as promises
export type PromisifiedPendpalChildMethods = {
    [K in keyof PenpalChildMethods]: (
        ...args: Parameters<PenpalChildMethods[K]>
    ) => Promise<ReturnType<PenpalChildMethods[K]>>;
};

export type PenpalChildMethods = PenpalChildMethodsType;

export const PENPAL_CHILD_CHANNEL = 'PENPAL_CHILD';
