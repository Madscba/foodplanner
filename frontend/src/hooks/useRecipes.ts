import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/endpoints';

// =============================================================================
// Query Keys
// =============================================================================

export const recipeKeys = {
  all: ['recipes'] as const,
  lists: () => [...recipeKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) =>
    [...recipeKeys.lists(), filters] as const,
  details: () => [...recipeKeys.all, 'detail'] as const,
  detail: (recipeId: string) => [...recipeKeys.details(), recipeId] as const,
  costs: () => [...recipeKeys.all, 'cost'] as const,
  cost: (recipeId: string) => [...recipeKeys.costs(), recipeId] as const,
  discounts: () => [...recipeKeys.all, 'discounts'] as const,
};

// =============================================================================
// Queries
// =============================================================================

export function useRecipes(params?: {
  name?: string;
  category?: string;
  area?: string;
  ingredient?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: recipeKeys.list(params ?? {}),
    queryFn: () => api.recipes.list(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useRecipe(recipeId: string) {
  return useQuery({
    queryKey: recipeKeys.detail(recipeId),
    queryFn: () => api.recipes.get(recipeId),
    enabled: !!recipeId,
  });
}

export function useRecipeCost(recipeId: string, preferDiscounts = true) {
  return useQuery({
    queryKey: recipeKeys.cost(recipeId),
    queryFn: () => api.recipes.getCost(recipeId, preferDiscounts),
    enabled: !!recipeId,
  });
}

export function useDiscountRecipes(params?: {
  min_discounted?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: [...recipeKeys.discounts(), params],
    queryFn: () => api.recipes.getByDiscounts(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// Mutations
// =============================================================================

export function useDeleteRecipe() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (recipeId: string) => api.recipes.delete(recipeId),
    onSuccess: (_, recipeId) => {
      queryClient.removeQueries({ queryKey: recipeKeys.detail(recipeId) });
      queryClient.invalidateQueries({ queryKey: recipeKeys.lists() });
    },
  });
}
