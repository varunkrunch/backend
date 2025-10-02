import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { useCreateNotebook } from '../hooks/useNotebooks';

export function CreateNotebookPage() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '',
    description: '',
  });

  const createNotebook = useCreateNotebook();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    try {
      const notebook = await createNotebook.mutateAsync({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
      });
      
      navigate(`/notebooks/${encodeURIComponent(notebook.name)}`);
    } catch (error) {
      console.error('Failed to create notebook:', error);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <Button
            variant="ghost"
            onClick={() => navigate(-1)}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Create New Notebook
          </h1>
          <p className="text-gray-600">
            Set up a new notebook to organize your research and sources
          </p>
        </div>

        {/* Form */}
        <div className="card p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <Input
              label="Notebook Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Enter a name for your notebook"
              required
              helperText="Choose a descriptive name that reflects the topic or purpose"
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description (Optional)
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="Describe what this notebook will be used for..."
              />
              <p className="text-sm text-gray-500 mt-1">
                Add a brief description to help you remember the purpose of this notebook
              </p>
            </div>

            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigate(-1)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                loading={createNotebook.isPending}
                disabled={!formData.name.trim()}
              >
                Create Notebook
              </Button>
            </div>
          </form>
        </div>

        {/* Tips */}
        <div className="mt-8 p-6 bg-blue-50 rounded-lg">
          <h3 className="font-medium text-blue-900 mb-2">Tips for organizing your notebook:</h3>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>• Use descriptive names that reflect your research topic</li>
            <li>• Add sources like PDFs, web pages, or text content</li>
            <li>• Use the chat feature to ask questions about your sources</li>
            <li>• Create notes to capture your insights and ideas</li>
          </ul>
        </div>
      </div>
    </div>
  );
}