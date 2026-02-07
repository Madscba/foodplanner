import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/endpoints';

// =============================================================================
// Query Keys
// =============================================================================

export const categoryKeys = {
  all: ['categories'] as const,
  list: () => [...categoryKeys.all, 'list'] as const,
};

export const areaKeys = {
  all: ['areas'] as const,
  list: () => [...areaKeys.all, 'list'] as const,
};

// =============================================================================
// Queries
// =============================================================================

export function useCategories() {
  return useQuery({
    queryKey: categoryKeys.list(),
    queryFn: () => api.categories.list(),
    staleTime: 30 * 60 * 1000, // 30 minutes - categories rarely change
  });
}

export function useAreas() {
  return useQuery({
    queryKey: areaKeys.list(),
    queryFn: () => api.areas.list(),
    staleTime: 30 * 60 * 1000, // 30 minutes - areas rarely change
  });
}
