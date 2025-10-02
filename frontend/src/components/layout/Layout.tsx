import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function Layout() {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar className="w-64 flex-shrink-0" />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}