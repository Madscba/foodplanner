import { Link } from 'react-router-dom';
import { ShoppingCart, Loader2 } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useShoppingList } from '@/hooks/useMealPlan';
import { formatCurrency } from '@/utils/cn';

interface ShoppingListPanelProps {
  planId: string;
}

export function ShoppingListPanel({ planId }: ShoppingListPanelProps) {
  const { data: shoppingList, isLoading, isError } = useShoppingList(planId);

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !shoppingList) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-sm text-muted-foreground">
            Failed to load shopping list
          </p>
        </CardContent>
      </Card>
    );
  }

  const itemCount = shoppingList.items.length;
  const hasSavings = shoppingList.total_savings > 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShoppingCart className="h-4 w-4" />
          Shopping List
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary stats */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Items</span>
            <span className="font-medium">{itemCount}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Estimated Cost</span>
            <span className="font-medium">
              {formatCurrency(shoppingList.total_cost)}
            </span>
          </div>
          {hasSavings && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">You Save</span>
              <Badge variant="savings">
                {formatCurrency(shoppingList.total_savings)}
              </Badge>
            </div>
          )}
        </div>

        {/* Quick preview of categories */}
        <div className="space-y-1">
          {Object.entries(shoppingList.items_by_category)
            .slice(0, 4)
            .map(([category, items]) => (
              <div
                key={category}
                className="flex items-center justify-between text-xs text-muted-foreground"
              >
                <span className="truncate">{category}</span>
                <span>{items.length} items</span>
              </div>
            ))}
          {Object.keys(shoppingList.items_by_category).length > 4 && (
            <p className="text-xs text-muted-foreground">
              +{Object.keys(shoppingList.items_by_category).length - 4} more
              categories
            </p>
          )}
        </div>

        {/* Link to full list */}
        <Button asChild className="w-full">
          <Link to={`/plan/shopping/${planId}`}>View Full List</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
