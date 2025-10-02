import React, { useState } from 'react';
import { Search, Filter, FileText, MessageSquare } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'text' | 'vector'>('text');
  const [filters, setFilters] = useState({
    sources: true,
    notes: true,
  });
  const [results, setResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      // TODO: Implement search API call
      console.log('Searching for:', query, { searchType, filters });
      
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      setResults([]);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Search
          </h1>
          <p className="text-gray-600">
            Search across all your notebooks, sources, and notes
          </p>
        </div>

        {/* Search Form */}
        <div className="card p-6 mb-8">
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search for anything..."
                  className="text-lg"
                />
              </div>
              <Button type="submit" size="lg" disabled={!query.trim() || isLoading}>
                {isLoading ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <Search className="h-5 w-5" />
                )}
              </Button>
            </div>

            {/* Search Options */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-200">
              <div className="flex items-center gap-4">
                <span className="text-sm font-medium text-gray-700">Search type:</span>
                <div className="flex items-center gap-2">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      value="text"
                      checked={searchType === 'text'}
                      onChange={(e) => setSearchType(e.target.value as 'text')}
                      className="mr-2"
                    />
                    <span className="text-sm">Text Search</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      value="vector"
                      checked={searchType === 'vector'}
                      onChange={(e) => setSearchType(e.target.value as 'vector')}
                      className="mr-2"
                    />
                    <span className="text-sm">Semantic Search</span>
                  </label>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <span className="text-sm font-medium text-gray-700">Include:</span>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={filters.sources}
                    onChange={(e) => setFilters({ ...filters, sources: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Sources</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={filters.notes}
                    onChange={(e) => setFilters({ ...filters, notes: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm">Notes</span>
                </label>
              </div>
            </div>
          </form>
        </div>

        {/* Results */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner size="lg" />
          </div>
        ) : results.length > 0 ? (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Search Results ({results.length})
            </h2>
            {results.map((result, index) => (
              <div key={index} className="card p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0">
                    {result.type === 'source' ? (
                      <FileText className="h-5 w-5 text-blue-600" />
                    ) : (
                      <MessageSquare className="h-5 w-5 text-green-600" />
                    )}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-900 mb-1">
                      {result.title}
                    </h3>
                    {result.snippet && (
                      <p className="text-sm text-gray-600 mb-2">
                        {result.snippet}
                      </p>
                    )}
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>Type: {result.type}</span>
                      {result.relevance && (
                        <span>Relevance: {Math.round(result.relevance * 100)}%</span>
                      )}
                      {result.similarity && (
                        <span>Similarity: {Math.round(result.similarity * 100)}%</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : query && !isLoading ? (
          <div className="text-center py-12">
            <Search className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No results found</h3>
            <p className="text-gray-600">
              Try adjusting your search terms or search type
            </p>
          </div>
        ) : (
          <div className="text-center py-12">
            <Search className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">Start searching</h3>
            <p className="text-gray-600">
              Enter a search query to find content across all your notebooks
            </p>
          </div>
        )}
      </div>
    </div>
  );
}