# Open Notebook Frontend

A modern React frontend for the Open Notebook backend, inspired by Google NotebookLM.

## Features

- **Notebook Management**: Create, edit, and organize notebooks
- **Source Management**: Add sources from text, URLs, or file uploads
- **AI Chat Interface**: Chat with your sources using AI models
- **Search**: Full-text and semantic search across all content
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Updates**: Live updates using React Query

## Tech Stack

- **React 18** with TypeScript
- **Vite** for fast development and building
- **Tailwind CSS** for styling
- **React Query** for data fetching and caching
- **React Router** for navigation
- **Axios** for API calls
- **Headless UI** for accessible components
- **Lucide React** for icons

## Getting Started

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and set your API base URL:
   ```
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```

4. **Open your browser** and navigate to `http://localhost:3000`

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── ui/             # Basic UI components (Button, Input, etc.)
│   ├── layout/         # Layout components (Sidebar, Layout)
│   ├── notebook/       # Notebook-specific components
│   └── chat/           # Chat interface components
├── hooks/              # Custom React hooks for API calls
├── lib/                # Utility functions and API client
├── pages/              # Page components
└── App.tsx             # Main application component
```

## Key Components

### Layout
- **Sidebar**: Navigation with notebook list and quick actions
- **Layout**: Main layout wrapper with sidebar and content area

### Notebook Management
- **NotebookHeader**: Notebook title, description, and actions
- **SourceCard**: Display source information with actions
- **AddSourceModal**: Modal for adding new sources

### Chat Interface
- **ChatInterface**: Real-time chat with AI models
- Supports message history and context

### UI Components
- **Button**: Styled button with variants and loading states
- **Input**: Form input with labels and validation
- **Modal**: Accessible modal dialogs
- **LoadingSpinner**: Loading indicators

## API Integration

The frontend communicates with the Open Notebook backend through a REST API. Key features:

- **Notebooks**: CRUD operations for notebooks
- **Sources**: Add sources from text, URLs, or file uploads
- **Chat**: Real-time chat with AI models
- **Search**: Text and semantic search capabilities

## Styling

The application uses Tailwind CSS for styling with a custom design system:

- **Colors**: Primary blue theme with semantic colors
- **Typography**: Inter font family with proper hierarchy
- **Components**: Consistent component styling with hover states
- **Responsive**: Mobile-first responsive design

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

### Code Style

- TypeScript for type safety
- ESLint for code quality
- Consistent naming conventions
- Component-based architecture

## Deployment

1. **Build the application**:
   ```bash
   npm run build
   ```

2. **Deploy the `dist` folder** to your hosting provider

3. **Configure environment variables** for production

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the Open Notebook system.