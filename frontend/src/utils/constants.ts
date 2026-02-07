export const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

export const DEFAULT_PEOPLE_COUNT = 2;
export const MIN_PEOPLE_COUNT = 1;
export const MAX_PEOPLE_COUNT = 20;

export const MAX_PLAN_DAYS = 30;

export const MEAL_TYPES = ['dinner'] as const;
export type MealType = (typeof MEAL_TYPES)[number];

export const DIETARY_PREFERENCES = [
  { name: 'Vegetarian', type: 'preference' },
  { name: 'Vegan', type: 'preference' },
  { name: 'Gluten-Free', type: 'restriction' },
  { name: 'Dairy-Free', type: 'restriction' },
  { name: 'Nut-Free', type: 'allergy' },
  { name: 'Shellfish-Free', type: 'allergy' },
  { name: 'Low-Carb', type: 'preference' },
  { name: 'High-Protein', type: 'preference' },
] as const;

export const CUISINE_AREAS = [
  'American',
  'British',
  'Chinese',
  'French',
  'Greek',
  'Indian',
  'Italian',
  'Japanese',
  'Mexican',
  'Thai',
  'Turkish',
  'Vietnamese',
] as const;
