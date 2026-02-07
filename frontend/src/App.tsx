import { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Toaster } from '@/components/ui/toaster';

// Lazy load pages for code splitting
const PlanSetup = lazy(() => import('@/pages/PlanSetup'));
const MealPlanView = lazy(() => import('@/pages/MealPlanView'));
const ShoppingList = lazy(() => import('@/pages/ShoppingList'));
const NotFound = lazy(() => import('@/pages/NotFound'));

function PageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-background">
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Navigate to="/plan/setup" replace />} />
          <Route path="/plan/setup" element={<PlanSetup />} />
          <Route path="/plan/view" element={<MealPlanView />} />
          <Route path="/plan/view/:planId" element={<MealPlanView />} />
          <Route path="/plan/shopping" element={<ShoppingList />} />
          <Route path="/plan/shopping/:planId" element={<ShoppingList />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
      <Toaster />
    </div>
  );
}

export default App;
