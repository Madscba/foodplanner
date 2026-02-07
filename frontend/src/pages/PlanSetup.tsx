import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { addDays, format, startOfDay } from 'date-fns';
import { CalendarIcon, ChefHat, Users, Leaf, X } from 'lucide-react';
import { DateRange } from 'react-day-picker';

import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/utils/cn';
import {
  DEFAULT_PEOPLE_COUNT,
  MIN_PEOPLE_COUNT,
  MAX_PEOPLE_COUNT,
  DIETARY_PREFERENCES,
} from '@/utils/constants';
import { usePreferencesStore } from '@/stores/preferencesStore';
import { useMealPlanStore } from '@/stores/mealPlanStore';
import { useCreateMealPlan } from '@/hooks/useMealPlan';
import { PeopleSelector } from '@/components/PeopleSelector';
import { PreferencesSelector } from '@/components/PreferencesSelector';

export default function PlanSetup() {
  const navigate = useNavigate();
  const { peopleCount, setPeopleCount, dietaryPreferences, togglePreference } =
    usePreferencesStore();
  const { setCurrentPlanId } = useMealPlanStore();
  const createMealPlan = useCreateMealPlan();

  const today = startOfDay(new Date());

  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: today,
    to: addDays(today, 6),
  });

  const handleGeneratePlan = async () => {
    if (!dateRange?.from || !dateRange?.to) return;

    try {
      const plan = await createMealPlan.mutateAsync({
        start_date: format(dateRange.from, 'yyyy-MM-dd'),
        end_date: format(dateRange.to, 'yyyy-MM-dd'),
        people_count: peopleCount,
        dietary_preferences: dietaryPreferences.map((name) => ({
          name,
          type:
            DIETARY_PREFERENCES.find((p) => p.name === name)?.type ??
            'preference',
        })),
        store_ids: [],
        user_id: 'default-user',
      });

      setCurrentPlanId(plan.id);
      navigate(`/plan/view/${plan.id}`);
    } catch (error) {
      console.error('Failed to create meal plan:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-green-50 to-white">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <ChefHat className="h-8 w-8 text-primary" />
            <span className="text-xl font-bold">Foodplanner</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="mx-auto max-w-2xl">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold tracking-tight">
              Plan Your Meals
            </h1>
            <p className="mt-2 text-muted-foreground">
              Select your dates and preferences, then let us generate a
              cost-effective meal plan using local discounts.
            </p>
          </div>

          <div className="space-y-6">
            {/* Date Selection */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CalendarIcon className="h-5 w-5" />
                  Select Dates
                </CardTitle>
                <CardDescription>
                  Choose the date range for your meal plan
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className={cn(
                          'flex-1 justify-start text-left font-normal',
                          !dateRange && 'text-muted-foreground'
                        )}
                      >
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {dateRange?.from ? (
                          dateRange.to ? (
                            <>
                              {format(dateRange.from, 'LLL dd, y')} -{' '}
                              {format(dateRange.to, 'LLL dd, y')}
                            </>
                          ) : (
                            format(dateRange.from, 'LLL dd, y')
                          )
                        ) : (
                          <span>Pick a date range</span>
                        )}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        initialFocus
                        mode="range"
                        defaultMonth={dateRange?.from}
                        selected={dateRange}
                        onSelect={setDateRange}
                        numberOfMonths={2}
                        disabled={{ before: today }}
                        fromDate={today}
                      />
                      <div className="border-t p-3">
                        <p className="text-xs text-muted-foreground">
                          Click a date to set start, then click another to set end.
                          Click a selected date to start over.
                        </p>
                      </div>
                    </PopoverContent>
                  </Popover>
                  {dateRange?.from && (
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => setDateRange(undefined)}
                      title="Clear dates"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                {dateRange?.from && dateRange?.to && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    {Math.ceil(
                      (dateRange.to.getTime() - dateRange.from.getTime()) /
                        (1000 * 60 * 60 * 24)
                    ) + 1}{' '}
                    days selected
                  </p>
                )}
              </CardContent>
            </Card>

            {/* People Selection */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Number of People
                </CardTitle>
                <CardDescription>
                  Recipes will be scaled to match the number of servings
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PeopleSelector
                  value={peopleCount}
                  onChange={setPeopleCount}
                  min={MIN_PEOPLE_COUNT}
                  max={MAX_PEOPLE_COUNT}
                />
              </CardContent>
            </Card>

            {/* Dietary Preferences */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Leaf className="h-5 w-5" />
                  Dietary Preferences
                </CardTitle>
                <CardDescription>
                  Select any dietary restrictions or preferences (optional)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PreferencesSelector
                  selected={dietaryPreferences}
                  onToggle={togglePreference}
                  options={DIETARY_PREFERENCES}
                />
              </CardContent>
            </Card>

            {/* Generate Button */}
            <Button
              size="lg"
              className="w-full"
              onClick={handleGeneratePlan}
              disabled={
                !dateRange?.from || !dateRange?.to || createMealPlan.isPending
              }
            >
              {createMealPlan.isPending ? (
                <>
                  <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Generating Plan...
                </>
              ) : (
                'Generate Meal Plan'
              )}
            </Button>

            {createMealPlan.isError && (
              <p className="text-center text-sm text-destructive">
                Failed to generate plan. Please try again.
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
