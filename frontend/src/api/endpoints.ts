import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import type {
  MealPlanCreateRequest,
  MealPlanResponse,
  MealPlanListResponse,
  MealPlanUpdateRequest,
  ShoppingListResponse,
  RecipeListResponse,
  RecipeResponse,
  RecipeCostEstimate,
  DiscountRecipesResponse,
  StoreDiscoveryResponse,
  CategoryListResponse,
  AreaListResponse,
  GraphStatsResponse,
} from './types';

// =============================================================================
// Meal Plan Endpoints
// =============================================================================

export const mealPlans = {
  create: (data: MealPlanCreateRequest) =>
    apiPost<MealPlanResponse>('/api/v1/meal-plans/', data),

  list: (params?: { user_id?: string; limit?: number; offset?: number }) =>
    apiGet<MealPlanListResponse>('/api/v1/meal-plans/', params),

  get: (planId: string) =>
    apiGet<MealPlanResponse>(`/api/v1/meal-plans/${planId}`),

  update: (planId: string, data: MealPlanUpdateRequest) =>
    apiPatch<MealPlanResponse>(`/api/v1/meal-plans/${planId}`, data),

  delete: (planId: string) => apiDelete(`/api/v1/meal-plans/${planId}`),

  getShoppingList: (planId: string) =>
    apiGet<ShoppingListResponse>(`/api/v1/meal-plans/${planId}/shopping-list`),
};

// =============================================================================
// Recipe Endpoints
// =============================================================================

export const recipes = {
  list: (params?: {
    name?: string;
    category?: string;
    area?: string;
    ingredient?: string;
    limit?: number;
    offset?: number;
  }) => apiGet<RecipeListResponse>('/api/v1/recipes', params),

  get: (recipeId: string) =>
    apiGet<RecipeResponse>(`/api/v1/recipes/${recipeId}`),

  getCost: (recipeId: string, preferDiscounts?: boolean) =>
    apiGet<RecipeCostEstimate>(`/api/v1/recipes/${recipeId}/cost`, {
      prefer_discounts: preferDiscounts,
    }),

  getByDiscounts: (params?: { min_discounted?: number; limit?: number }) =>
    apiGet<DiscountRecipesResponse>('/api/v1/recipes/by-discounts', params),

  delete: (recipeId: string) => apiDelete(`/api/v1/recipes/${recipeId}`),
};

// =============================================================================
// Store Endpoints
// =============================================================================

export const stores = {
  discover: (params?: { zip_code?: string; brand?: string; limit?: number }) =>
    apiGet<StoreDiscoveryResponse>('/api/v1/stores/discover', params),

  get: (storeId: string) =>
    apiGet<{ id: string; name: string; brand: string }>(
      `/api/v1/stores/${storeId}`
    ),
};

// =============================================================================
// Category & Area Endpoints
// =============================================================================

export const categories = {
  list: () => apiGet<CategoryListResponse>('/api/v1/categories'),
};

export const areas = {
  list: () => apiGet<AreaListResponse>('/api/v1/areas'),
};

// =============================================================================
// Graph Stats
// =============================================================================

export const graph = {
  stats: () => apiGet<GraphStatsResponse>('/api/v1/graph/stats'),
};

// =============================================================================
// Combined API Object
// =============================================================================

export const api = {
  mealPlans,
  recipes,
  stores,
  categories,
  areas,
  graph,
};

export default api;
