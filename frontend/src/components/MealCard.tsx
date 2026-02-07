import { useState } from 'react';
import {
  GripVertical,
  Lock,
  Unlock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn, formatCurrency } from '@/utils/cn';
import type { RecipeInPlan } from '@/api/types';

interface MealCardProps {
  recipe: RecipeInPlan;
  onToggleLock?: () => void;
  onReplace?: () => void;
  onViewDetails?: () => void;
  isDraggable?: boolean;
}

export function MealCard({
  recipe,
  onToggleLock,
  onReplace,
  onViewDetails,
  isDraggable = true,
}: MealCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `${recipe.scheduled_date}-${recipe.meal_type}-${recipe.id}`,
    disabled: !isDraggable || recipe.is_locked,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const hasSavings = (recipe.estimated_savings ?? 0) > 0;

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        'relative transition-shadow',
        isDragging && 'shadow-lg ring-2 ring-primary',
        recipe.is_locked && 'border-primary/50 bg-primary/5'
      )}
    >
      <CardContent className="p-3">
        {/* Header with drag handle and actions */}
        <div className="flex items-start gap-2">
          {isDraggable && (
            <button
              {...attributes}
              {...listeners}
              className={cn(
                'mt-1 cursor-grab touch-none text-muted-foreground hover:text-foreground',
                recipe.is_locked && 'cursor-not-allowed opacity-50'
              )}
              disabled={recipe.is_locked}
            >
              <GripVertical className="h-4 w-4" />
            </button>
          )}

          <div className="flex-1 min-w-0">
            {/* Recipe thumbnail and name */}
            <div className="flex items-start gap-3">
              {recipe.thumbnail ? (
                <img
                  src={recipe.thumbnail}
                  alt={recipe.name}
                  className="h-12 w-12 rounded-md object-cover"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-md bg-muted">
                  <span className="text-lg">🍽️</span>
                </div>
              )}

              <div className="flex-1 min-w-0">
                <h4 className="font-medium leading-tight truncate">
                  {recipe.name}
                </h4>
                <p className="text-sm text-muted-foreground">
                  {recipe.servings} servings
                </p>
              </div>
            </div>

            {/* Cost and savings */}
            <div className="mt-2 flex items-center gap-2">
              {recipe.estimated_cost !== null && (
                <span className="text-sm font-medium">
                  {formatCurrency(recipe.estimated_cost)}
                </span>
              )}
              {hasSavings && (
                <Badge variant="savings" className="text-xs">
                  Save {formatCurrency(recipe.estimated_savings!)}
                </Badge>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-1">
            {onToggleLock && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onToggleLock}
                title={recipe.is_locked ? 'Unlock' : 'Lock'}
              >
                {recipe.is_locked ? (
                  <Lock className="h-3.5 w-3.5 text-primary" />
                ) : (
                  <Unlock className="h-3.5 w-3.5" />
                )}
              </Button>
            )}
            {onReplace && !recipe.is_locked && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onReplace}
                title="Replace"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>

        {/* Expand/collapse button */}
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full h-6 text-xs"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? (
            <>
              <ChevronUp className="mr-1 h-3 w-3" />
              Less details
            </>
          ) : (
            <>
              <ChevronDown className="mr-1 h-3 w-3" />
              More details
            </>
          )}
        </Button>

        {/* Expanded details */}
        {isExpanded && (
          <div className="mt-2 pt-2 border-t space-y-2">
            {hasSavings && (
              <p className="text-xs text-muted-foreground">
                💡 This recipe uses discounted ingredients
              </p>
            )}
            {onViewDetails && (
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={onViewDetails}
              >
                <ExternalLink className="mr-2 h-3 w-3" />
                View full recipe
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
