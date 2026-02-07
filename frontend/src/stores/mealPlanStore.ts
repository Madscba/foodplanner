import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { RecipeInPlan } from '@/api/types';

interface MealSlot {
  date: string; // ISO date
  mealType: string;
  recipe: RecipeInPlan | null;
  isLocked: boolean;
}

interface MealPlanState {
  // Current plan ID
  currentPlanId: string | null;
  setCurrentPlanId: (id: string | null) => void;

  // Draft plan (local edits before saving)
  draftSlots: Record<string, MealSlot>; // key: `${date}-${mealType}`
  setDraftSlot: (date: string, mealType: string, recipe: RecipeInPlan | null) => void;
  toggleLockSlot: (date: string, mealType: string) => void;
  clearDraft: () => void;

  // Track unsaved changes
  hasUnsavedChanges: boolean;
  setHasUnsavedChanges: (value: boolean) => void;

  // Initialize draft from plan data
  initializeDraft: (recipes: RecipeInPlan[]) => void;

  // Get slot by key
  getSlot: (date: string, mealType: string) => MealSlot | undefined;
}

const createSlotKey = (date: string, mealType: string) => `${date}-${mealType}`;

export const useMealPlanStore = create<MealPlanState>()(
  persist(
    (set, get) => ({
      currentPlanId: null,
      draftSlots: {},
      hasUnsavedChanges: false,

      setCurrentPlanId: (id) =>
        set({
          currentPlanId: id,
          draftSlots: {},
          hasUnsavedChanges: false,
        }),

      setDraftSlot: (date, mealType, recipe) =>
        set((state) => ({
          draftSlots: {
            ...state.draftSlots,
            [createSlotKey(date, mealType)]: {
              date,
              mealType,
              recipe,
              isLocked: state.draftSlots[createSlotKey(date, mealType)]?.isLocked ?? false,
            },
          },
          hasUnsavedChanges: true,
        })),

      toggleLockSlot: (date, mealType) =>
        set((state) => {
          const key = createSlotKey(date, mealType);
          const existing = state.draftSlots[key];
          if (!existing) return state;

          return {
            draftSlots: {
              ...state.draftSlots,
              [key]: {
                ...existing,
                isLocked: !existing.isLocked,
              },
            },
            hasUnsavedChanges: true,
          };
        }),

      clearDraft: () =>
        set({
          draftSlots: {},
          hasUnsavedChanges: false,
        }),

      setHasUnsavedChanges: (value) => set({ hasUnsavedChanges: value }),

      initializeDraft: (recipes) =>
        set({
          draftSlots: recipes.reduce(
            (acc, recipe) => {
              const key = createSlotKey(recipe.scheduled_date, recipe.meal_type);
              acc[key] = {
                date: recipe.scheduled_date,
                mealType: recipe.meal_type,
                recipe,
                isLocked: recipe.is_locked,
              };
              return acc;
            },
            {} as Record<string, MealSlot>
          ),
          hasUnsavedChanges: false,
        }),

      getSlot: (date, mealType) => {
        const key = createSlotKey(date, mealType);
        return get().draftSlots[key];
      },
    }),
    {
      name: 'foodplanner-meal-plan',
      version: 1,
      partialize: (state) => ({
        currentPlanId: state.currentPlanId,
      }),
    }
  )
);
