'use client';

// TODO: Build-Factory integration - posthog/Project/Branch wiring removed; minimal provider.
import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { EditorEngine } from './engine';

const EditorEngineContext = createContext<EditorEngine | null>(null);

export const useEditorEngine = () => {
    const ctx = useContext(EditorEngineContext);
    if (!ctx) throw new Error('useEditorEngine must be inside EditorEngineProvider');
    return ctx;
};

export const EditorEngineProvider = ({
    children,
    projectId,
}: {
    children: ReactNode;
    projectId: string;
}) => {
    const engineRef = useRef<EditorEngine | null>(null);
    const [editorEngine] = useState(() => {
        const engine = new EditorEngine(projectId);
        engine.initBranches([]);
        engine.init();
        engineRef.current = engine;
        return engine;
    });

    return (
        <EditorEngineContext.Provider value={editorEngine}>
            {children}
        </EditorEngineContext.Provider>
    );
};
