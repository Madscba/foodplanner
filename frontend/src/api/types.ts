// =============================================================================
// API Types - Mirroring backend schemas
// =============================================================================

// Dietary preferences
export interface DietaryPreference {
  name: string;
  type: 'allergy' | 'preference' | 'restriction';
}

// =============================================================================
// Meal Plan Types
// =============================================================================

export interface MealPlanCreateRequest {
  user_id?: string;
  store_ids?: string[];
  start_date: string; // ISO date format: YYYY-MM-DD
  end_date: string;
  people_count: number;
  dietary_preferences?: DietaryPreference[];
  budget_max?: number;
  on_hand_ingredients?: string[];
  preselected_recipe_ids?: string[];
}

export interface MealSlotUpdate {
  scheduled_date: string;
  meal_type: string;
  recipe_id: string | null;
  is_locked?: boolean;
}

export interface MealPlanUpdateRequest {
  meals?: MealSlotUpdate[];
}

export interface RecipeInPlan {
  id: string;
  name: string;
  thumbnail: string | null;
  scheduled_date: string;
  meal_type: string;
  servings: number;
  estimated_cost: number | null;
  estimated_savings: number | null;
  is_locked: boolean;
}

export interface MealPlanResponse {
  id: string;
  user_id: string;
  start_date: string;
  end_date: string;
  people_count: number;
  total_cost: number;
  total_savings: number;
  recipes: RecipeInPlan[];
  created_at: string;
}

export interface MealPlanListResponse {
  plans: MealPlanResponse[];
  total: number;
}

// =============================================================================
// Shopping List Types
// =============================================================================

export interface ShoppingListItem {
  ingredient_name: string;
  quantity: string;
  unit: string;
  product_name: string | null;
  product_id: string | null;
  price: number | null;
  discount_price: number | null;
  store_name: string | null;
  category: string | null;
}

export interface ShoppingListResponse {
  meal_plan_id: string;
  items: ShoppingListItem[];
  total_cost: number;
  total_savings: number;
  items_by_category: Record<string, ShoppingListItem[]>;
}

// =============================================================================
// Recipe Types (from graph models)
// =============================================================================

export interface IngredientDetail {
  name: string;
  normalized_name: string;
  quantity: string;
  measure: string;
}

export interface Recipe {
  id: string;
  name: string;
  instructions: string;
  thumbnail: string | null;
  source_url: string | null;
  youtube_url: string | null;
  tags: string[];
  category: string | null;
  area: string | null;
  ingredients: IngredientDetail[];
}

export interface RecipeListResponse {
  recipes: Recipe[];
  total: number;
  offset: number;
  limit: number;
}

export interface RecipeResponse {
  recipe: Recipe;
}

export interface RecipeCostEstimate {
  recipe_id: string;
  recipe_name: string;
  items: CostItem[];
  total_cost: number;
  total_savings: number;
}

export interface CostItem {
  ingredient_name: string;
  product_name: string | null;
  price: number | null;
  discount_price: number | null;
}

export interface RecipeSearchResult {
  recipe: Recipe;
  matched_ingredients: number;
  discounted_ingredients: number;
  total_ingredients: number;
  estimated_cost: number | null;
  estimated_savings: number | null;
}

export interface DiscountRecipesResponse {
  recipes: RecipeSearchResult[];
  total: number;
}

// =============================================================================
// Store Types
// =============================================================================

export interface Store {
  id: string;
  name: string;
  brand: string;
  address: string | null;
  city: string | null;
  zip_code: string | null;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
}

export interface StoreDiscoveryResponse {
  stores: Store[];
  total: number;
  source: string;
}

// =============================================================================
// Category & Area Types
// =============================================================================

export interface Category {
  name: string;
  description: string | null;
  thumbnail: string | null;
}

export interface CategoryListResponse {
  categories: Category[];
  total: number;
}

export interface Area {
  name: string;
}

export interface AreaListResponse {
  areas: Area[];
  total: number;
}

// =============================================================================
// Graph Stats
// =============================================================================

export interface GraphStatsResponse {
  recipes: number;
  ingredients: number;
  products: number;
  categories: number;
  areas: number;
  stores: number;
  matches: number;
}
