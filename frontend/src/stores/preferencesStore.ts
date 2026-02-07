import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { DEFAULT_PEOPLE_COUNT } from '@/utils/constants';

interface PreferencesState {
  // People count
  peopleCount: number;
  setPeopleCount: (count: number) => void;

  // Dietary preferences (list of preference names)
  dietaryPreferences: string[];
  togglePreference: (preference: string) => void;
  setDietaryPreferences: (preferences: string[]) => void;
  clearPreferences: () => void;

  // Selected stores
  selectedStoreIds: string[];
  toggleStore: (storeId: string) => void;
  setSelectedStores: (storeIds: string[]) => void;

  // Budget
  budgetMax: number | null;
  setBudgetMax: (budget: number | null) => void;

  // Reset all
  resetAll: () => void;
}

const initialState = {
  peopleCount: DEFAULT_PEOPLE_COUNT,
  dietaryPreferences: [],
  selectedStoreIds: [],
  budgetMax: null,
};

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      ...initialState,

      setPeopleCount: (count) =>
        set({ peopleCount: Math.max(1, Math.min(20, count)) }),

      togglePreference: (preference) =>
        set((state) => ({
          dietaryPreferences: state.dietaryPreferences.includes(preference)
            ? state.dietaryPreferences.filter((p) => p !== preference)
            : [...state.dietaryPreferences, preference],
        })),

      setDietaryPreferences: (preferences) =>
        set({ dietaryPreferences: preferences }),

      clearPreferences: () => set({ dietaryPreferences: [] }),

      toggleStore: (storeId) =>
        set((state) => ({
          selectedStoreIds: state.selectedStoreIds.includes(storeId)
            ? state.selectedStoreIds.filter((id) => id !== storeId)
            : [...state.selectedStoreIds, storeId],
        })),

      setSelectedStores: (storeIds) => set({ selectedStoreIds: storeIds }),

      setBudgetMax: (budget) => set({ budgetMax: budget }),

      resetAll: () => set(initialState),
    }),
    {
      name: 'foodplanner-preferences',
      version: 1,
    }
  )
);
