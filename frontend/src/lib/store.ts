import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LLMProvider } from "./api";

interface AppState {
  provider: LLMProvider;
  model: string;
  setProvider: (p: LLMProvider) => void;
  setModel: (m: string) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      provider: "ollama",
      model: "",
      setProvider: (provider) => set({ provider, model: "" }),
      setModel: (model) => set({ model }),
    }),
    { name: "company-os-settings" }
  )
);
