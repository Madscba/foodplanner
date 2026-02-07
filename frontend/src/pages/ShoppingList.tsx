import { useParams, Link } from 'react-router-dom';
import {
  ChefHat,
  ArrowLeft,
  Printer,
  Copy,
  Check,
  Loader2,
  ShoppingBag,
} from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useShoppingList } from '@/hooks/useMealPlan';
import { useMealPlanStore } from '@/stores/mealPlanStore';
import { formatCurrency } from '@/utils/cn';

export default function ShoppingList() {
  const { planId } = useParams<{ planId: string }>();
  const { currentPlanId } = useMealPlanStore();
  const [copied, setCopied] = useState(false);

  const effectivePlanId = planId ?? currentPlanId;

  const {
    data: shoppingList,
    isLoading,
    isError,
  } = useShoppingList(effectivePlanId ?? '');

  const handleCopyList = async () => {
    if (!shoppingList) return;

    const text = Object.entries(shoppingList.items_by_category)
      .map(([category, items]) => {
        const itemLines = items
          .map(
            (item) =>
              `- ${item.ingredient_name}${item.quantity ? ` (${item.quantity} ${item.unit})` : ''}`
          )
          .join('\n');
        return `${category}:\n${itemLines}`;
      })
      .join('\n\n');

    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
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

  if (isError || !shoppingList) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Card className="w-96">
          <CardContent className="pt-6 text-center">
            <p className="mb-4 text-destructive">
              Failed to load shopping list
            </p>
            <Button asChild variant="outline">
              <Link to={`/plan/view/${effectivePlanId}`}>Go Back</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const categories = Object.entries(shoppingList.items_by_category);

  return (
    <div className="min-h-screen bg-background print:bg-white">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b bg-white/80 backdrop-blur-sm print:hidden">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" asChild>
              <Link to={`/plan/view/${effectivePlanId}`}>
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <ChefHat className="h-6 w-6 text-primary" />
              <span className="text-lg font-semibold">Shopping List</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={handleCopyList}>
              {copied ? (
                <>
                  <Check className="mr-2 h-4 w-4" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="mr-2 h-4 w-4" />
                  Copy List
                </>
              )}
            </Button>
            <Button variant="outline" onClick={handlePrint}>
              <Printer className="mr-2 h-4 w-4" />
              Print
            </Button>
          </div>
        </div>
      </header>

      {/* Print Header */}
      <div className="hidden print:block print:p-4">
        <h1 className="text-2xl font-bold">Shopping List</h1>
        <p className="text-sm text-gray-500">
          Total: {formatCurrency(shoppingList.total_cost)}
        </p>
      </div>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {/* Summary Cards */}
        <div className="mb-6 grid gap-4 md:grid-cols-3 print:hidden">
          <Card>
            <CardContent className="flex items-center gap-4 pt-6">
              <div className="rounded-full bg-primary/10 p-3">
                <ShoppingBag className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Items</p>
                <p className="text-2xl font-bold">{shoppingList.items.length}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4 pt-6">
              <div className="rounded-full bg-primary/10 p-3">
                <span className="text-xl font-bold text-primary">kr</span>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Estimated Cost</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(shoppingList.total_cost)}
                </p>
              </div>
            </CardContent>
          </Card>

          {shoppingList.total_savings > 0 && (
            <Card className="border-savings bg-savings-light/30">
              <CardContent className="flex items-center gap-4 pt-6">
                <Badge variant="savings" className="h-12 w-12 justify-center text-lg">
                  %
                </Badge>
                <div>
                  <p className="text-sm text-muted-foreground">You Save</p>
                  <p className="text-2xl font-bold text-savings">
                    {formatCurrency(shoppingList.total_savings)}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Shopping List by Category */}
        <div className="space-y-6">
          {categories.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <ShoppingBag className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
                <p className="text-muted-foreground">
                  No items in your shopping list
                </p>
              </CardContent>
            </Card>
          ) : (
            categories.map(([category, items]) => (
              <Card key={category} className="print:border-none print:shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">{category}</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="divide-y">
                    {items.map((item, index) => (
                      <li
                        key={`${item.ingredient_name}-${index}`}
                        className="flex items-center justify-between py-3"
                      >
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            className="h-5 w-5 rounded border-gray-300 text-primary focus:ring-primary"
                          />
                          <div>
                            <p className="font-medium">{item.ingredient_name}</p>
                            {item.product_name && (
                              <p className="text-sm text-muted-foreground">
                                {item.product_name}
                                {item.store_name && ` · ${item.store_name}`}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="text-right">
                          {item.quantity && (
                            <p className="text-sm text-muted-foreground">
                              {item.quantity} {item.unit}
                            </p>
                          )}
                          {item.price && (
                            <div className="flex items-center gap-2">
                              {item.discount_price ? (
                                <>
                                  <span className="text-sm text-muted-foreground line-through">
                                    {formatCurrency(item.price)}
                                  </span>
                                  <span className="font-medium text-savings">
                                    {formatCurrency(item.discount_price)}
                                  </span>
                                </>
                              ) : (
                                <span className="font-medium">
                                  {formatCurrency(item.price)}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
