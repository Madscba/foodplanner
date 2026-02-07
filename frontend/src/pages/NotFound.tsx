import { Link } from 'react-router-dom';
import { ChefHat, Home } from 'lucide-react';

import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-green-50 to-white">
      <ChefHat className="mb-4 h-16 w-16 text-muted-foreground" />
      <h1 className="mb-2 text-4xl font-bold">404</h1>
      <p className="mb-8 text-muted-foreground">
        Oops! This page doesn't exist.
      </p>
      <Button asChild>
        <Link to="/">
          <Home className="mr-2 h-4 w-4" />
          Go Home
        </Link>
      </Button>
    </div>
  );
}
