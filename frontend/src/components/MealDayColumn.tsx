import { format } from 'date-fns';
import { Plus } from 'lucide-react';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { MealCard } from '@/components/MealCard';
import { useMealPlanStore } from '@/stores/mealPlanStore';
import type { RecipeInPlan } from '@/api/types';

interface MealDayColumnProps {
  date: Date;
  recipes: RecipeInPlan[];
  planId: string;
}

export function MealDayColumn({ date, recipes, planId }: MealDayColumnProps) {
  const { toggleLockSlot } = useMealPlanStore();

  const dateKey = format(date, 'yyyy-MM-dd');
  const isToday = format(new Date(), 'yyyy-MM-dd') === dateKey;

  const handleToggleLock = (recipe: RecipeInPlan) => {
    toggleLockSlot(recipe.scheduled_date, recipe.meal_type);
  };

  const handleReplace = (recipe: RecipeInPlan) => {
    // TODO: Open recipe replacement sheet
    console.log('Replace recipe:', recipe.id);
  };

  const handleViewDetails = (recipe: RecipeInPlan) => {
    // TODO: Open recipe detail sheet
    console.log('View details:', recipe.id);
  };

  const handleAddMeal = () => {
    // TODO: Open recipe search/add sheet
    console.log('Add meal for:', dateKey);
  };

  // Get sortable IDs for dnd-kit
  const sortableIds = recipes.map(
    (r) => `${r.scheduled_date}-${r.meal_type}-${r.id}`
  );

  return (
    <Card className={isToday ? 'ring-2 ring-primary' : ''}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-base">
          <span>{format(date, 'EEE')}</span>
          <span
            className={`text-sm ${isToday ? 'font-bold text-primary' : 'font-normal text-muted-foreground'}`}
          >
            {format(date, 'MMM d')}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <SortableContext
          items={sortableIds}
          strategy={verticalListSortingStrategy}
        >
          {recipes.length > 0 ? (
            recipes.map((recipe) => (
              <MealCard
                key={`${recipe.scheduled_date}-${recipe.meal_type}-${recipe.id}`}
                recipe={recipe}
                onToggleLock={() => handleToggleLock(recipe)}
                onReplace={() => handleReplace(recipe)}
                onViewDetails={() => handleViewDetails(recipe)}
              />
            ))
          ) : (
            <div className="py-4 text-center">
              <p className="text-sm text-muted-foreground mb-2">No meal planned</p>
            </div>
          )}
        </SortableContext>

        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={handleAddMeal}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Meal
        </Button>
      </CardContent>
    </Card>
  );
}
