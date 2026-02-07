import { create } from 'zustand';
import type { ShoppingListItem } from '@/api/types';

interface ShoppingListState {
  // Items checked off by the user
  checkedItems: Set<string>;
  toggleChecked: (itemKey: string) => void;
  clearChecked: () => void;
  isChecked: (itemKey: string) => boolean;

  // Custom items added by user (not from recipes)
  customItems: ShoppingListItem[];
  addCustomItem: (item: Omit<ShoppingListItem, 'product_id' | 'product_name'>) => void;
  removeCustomItem: (ingredientName: string) => void;
  clearCustomItems: () => void;

  // Items to exclude (user already has them)
  excludedItems: Set<string>;
  toggleExcluded: (itemKey: string) => void;
  clearExcluded: () => void;
  isExcluded: (itemKey: string) => boolean;
}

const createItemKey = (ingredientName: string) =>
  ingredientName.toLowerCase().trim();

export const useShoppingListStore = create<ShoppingListState>()((set, get) => ({
  checkedItems: new Set(),
  customItems: [],
  excludedItems: new Set(),

  toggleChecked: (itemKey) =>
    set((state) => {
      const newChecked = new Set(state.checkedItems);
      if (newChecked.has(itemKey)) {
        newChecked.delete(itemKey);
      } else {
        newChecked.add(itemKey);
      }
      return { checkedItems: newChecked };
    }),

  clearChecked: () => set({ checkedItems: new Set() }),

  isChecked: (itemKey) => get().checkedItems.has(itemKey),

  addCustomItem: (item) =>
    set((state) => ({
      customItems: [
        ...state.customItems,
        {
          ...item,
          product_id: null,
          product_name: null,
        },
      ],
    })),

  removeCustomItem: (ingredientName) =>
    set((state) => ({
      customItems: state.customItems.filter(
        (item) => createItemKey(item.ingredient_name) !== createItemKey(ingredientName)
      ),
    })),

  clearCustomItems: () => set({ customItems: [] }),

  toggleExcluded: (itemKey) =>
    set((state) => {
      const newExcluded = new Set(state.excludedItems);
      if (newExcluded.has(itemKey)) {
        newExcluded.delete(itemKey);
      } else {
        newExcluded.add(itemKey);
      }
      return { excludedItems: newExcluded };
    }),

  clearExcluded: () => set({ excludedItems: new Set() }),

  isExcluded: (itemKey) => get().excludedItems.has(itemKey),
}));

// Helper to create consistent item keys
export const getItemKey = createItemKey;
