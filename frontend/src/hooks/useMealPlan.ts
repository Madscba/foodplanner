import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/endpoints';
import type {
  MealPlanCreateRequest,
  MealPlanUpdateRequest,
  MealPlanResponse,
  ShoppingListResponse,
} from '@/api/types';

// =============================================================================
// Query Keys
// =============================================================================

export const mealPlanKeys = {
  all: ['mealPlans'] as const,
  lists: () => [...mealPlanKeys.all, 'list'] as const,
  list: (userId: string) => [...mealPlanKeys.lists(), userId] as const,
  details: () => [...mealPlanKeys.all, 'detail'] as const,
  detail: (planId: string) => [...mealPlanKeys.details(), planId] as const,
  shoppingLists: () => [...mealPlanKeys.all, 'shoppingList'] as const,
  shoppingList: (planId: string) =>
    [...mealPlanKeys.shoppingLists(), planId] as const,
};

// =============================================================================
// Queries
// =============================================================================

export function useMealPlan(planId: string) {
  return useQuery({
    queryKey: mealPlanKeys.detail(planId),
    queryFn: () => api.mealPlans.get(planId),
    enabled: !!planId,
  });
}

export function useMealPlanList(userId: string = 'default-user') {
  return useQuery({
    queryKey: mealPlanKeys.list(userId),
    queryFn: () => api.mealPlans.list({ user_id: userId }),
  });
}

export function useShoppingList(planId: string) {
  return useQuery({
    queryKey: mealPlanKeys.shoppingList(planId),
    queryFn: () => api.mealPlans.getShoppingList(planId),
    enabled: !!planId,
  });
}

// =============================================================================
// Mutations
// =============================================================================

export function useCreateMealPlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: MealPlanCreateRequest) => api.mealPlans.create(data),
    onSuccess: (newPlan) => {
      // Add new plan to cache
      queryClient.setQueryData(mealPlanKeys.detail(newPlan.id), newPlan);
      // Invalidate list queries
      queryClient.invalidateQueries({ queryKey: mealPlanKeys.lists() });
    },
  });
}

export function useUpdateMealPlan(planId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: MealPlanUpdateRequest) =>
      api.mealPlans.update(planId, data),
    onSuccess: (updatedPlan) => {
      // Update plan in cache
      queryClient.setQueryData(mealPlanKeys.detail(planId), updatedPlan);
      // Invalidate shopping list
      queryClient.invalidateQueries({
        queryKey: mealPlanKeys.shoppingList(planId),
      });
    },
  });
}

export function useDeleteMealPlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (planId: string) => api.mealPlans.delete(planId),
    onSuccess: (_, planId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: mealPlanKeys.detail(planId) });
      queryClient.removeQueries({ queryKey: mealPlanKeys.shoppingList(planId) });
      // Invalidate list queries
      queryClient.invalidateQueries({ queryKey: mealPlanKeys.lists() });
    },
  });
}
