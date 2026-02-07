import { useParams, useNavigate, Link } from 'react-router-dom';
import { format, parseISO, eachDayOfInterval } from 'date-fns';
import {
  ChefHat,
  ShoppingCart,
  ArrowLeft,
  GripVertical,
  Lock,
  Unlock,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import {
  DndContext,
  DragEndEvent,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useMealPlan } from '@/hooks/useMealPlan';
import { useMealPlanStore } from '@/stores/mealPlanStore';
import { formatCurrency } from '@/utils/cn';
import { MealCard } from '@/components/MealCard';
import { MealDayColumn } from '@/components/MealDayColumn';
import { ShoppingListPanel } from '@/components/ShoppingListPanel';

export default function MealPlanView() {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();
  const { currentPlanId } = useMealPlanStore();

  const effectivePlanId = planId ?? currentPlanId;

  const { data: plan, isLoading, isError } = useMealPlan(effectivePlanId ?? '');

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    // Handle meal reordering logic here
    console.log('Dragged', active.id, 'over', over.id);
  };

  if (!effectivePlanId) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Card className="w-96">
          <CardContent className="pt-6 text-center">
            <p className="mb-4 text-muted-foreground">No meal plan selected</p>
            <Button asChild>
              <Link to="/plan/setup">Create a Plan</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isError || !plan) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Card className="w-96">
          <CardContent className="pt-6 text-center">
            <p className="mb-4 text-destructive">Failed to load meal plan</p>
            <Button asChild variant="outline">
              <Link to="/plan/setup">Go Back</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const days = eachDayOfInterval({
    start: parseISO(plan.start_date),
    end: parseISO(plan.end_date),
  });

  // Group recipes by date
  const recipesByDate = plan.recipes.reduce(
    (acc, recipe) => {
      const dateKey = recipe.scheduled_date;
      if (!acc[dateKey]) {
        acc[dateKey] = [];
      }
      acc[dateKey].push(recipe);
      return acc;
    },
    {} as Record<string, typeof plan.recipes>
  );

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b bg-white/80 backdrop-blur-sm">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" asChild>
              <Link to="/plan/setup">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <ChefHat className="h-6 w-6 text-primary" />
              <span className="text-lg font-semibold">Meal Plan</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Estimated Cost</p>
              <p className="font-semibold">{formatCurrency(plan.total_cost)}</p>
            </div>
            {plan.total_savings > 0 && (
              <Badge variant="savings">
                Save {formatCurrency(plan.total_savings)}
              </Badge>
            )}
            <Button asChild>
              <Link to={`/plan/shopping/${effectivePlanId}`}>
                <ShoppingCart className="mr-2 h-4 w-4" />
                Shopping List
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">
              {format(parseISO(plan.start_date), 'MMM d')} -{' '}
              {format(parseISO(plan.end_date), 'MMM d, yyyy')}
            </h1>
            <p className="text-muted-foreground">
              {plan.people_count} {plan.people_count === 1 ? 'person' : 'people'}{' '}
              · {days.length} days
            </p>
          </div>
        </div>

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {days.map((day) => {
              const dateKey = format(day, 'yyyy-MM-dd');
              const dayRecipes = recipesByDate[dateKey] ?? [];

              return (
                <MealDayColumn
                  key={dateKey}
                  date={day}
                  recipes={dayRecipes}
                  planId={effectivePlanId}
                />
              );
            })}
          </div>
        </DndContext>
      </main>
    </div>
  );
}
