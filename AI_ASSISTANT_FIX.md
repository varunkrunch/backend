# 🤖 AI Assistant Fix Guide

## 🚨 **Problem Identified**

The error **"Error generating response: Model is not a LanguageModel: None"** occurs because:

1. **Namespace Mismatch**: The backend was using `open_notebook:default_models` but the database namespace is now `fastapi_backend`
2. **Missing Default Models**: No default model configuration exists in the database
3. **Hardcoded Paths**: Some paths were still pointing to the original OpenNotebook location

## ✅ **Fixes Applied**

### **1. Fixed Namespace Issues**
- ✅ Updated `DefaultModels.record_id` from `"open_notebook:default_models"` to `"fastapi_backend:default_models"`
- ✅ Updated `DefaultPrompts.record_id` from `"open_notebook:default_prompts"` to `"fastapi_backend:default_prompts"`
- ✅ Updated `ContentSettings.record_id` from `"open_notebook:content_settings"` to `"fastapi_backend:content_settings"`
- ✅ Updated `DEFAULT_MODELS_RECORD` in models router

### **2. Fixed Hardcoded Paths**
- ✅ Updated prompt directory path in `chat.py` to use relative paths
- ✅ Removed hardcoded `/Users/varun/open-notebook/prompts` path

### **3. Created Model Initialization Script**
- ✅ Added `init_models.py` to set up default models in database
- ✅ Updated `install-dependencies.sh` to run model initialization

## 🛠️ **How to Fix the AI Assistant**

### **Step 1: Update the Backend**
```bash
# Pull the latest changes
git pull origin new-main

# Or if cloning fresh:
git clone https://github.com/22PA1A45B4/backend.git
cd backend
```

### **Step 2: Install Dependencies**
```bash
# Use the updated installation script
./install-dependencies.sh
```

### **Step 3: Set Up Environment Variables**
Create a `.env` file in the backend directory:
```bash
# Required API keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Database configuration
SURREAL_NAMESPACE=fastapi_backend
SURREAL_DATABASE=production
SURREAL_URL=ws://localhost:8000/rpc
```

### **Step 4: Initialize Models (if not done automatically)**
```bash
python init_models.py
```

### **Step 5: Start the Backend**
```bash
python run.py
```

## 🔍 **Verification Steps**

### **Test 1: Check Model Initialization**
```bash
# Run the model initialization script
python init_models.py

# Should see:
# ✅ Default models configuration saved
# ✅ Created model: gpt-4o-mini
# ✅ Created model: gpt-4o
# ✅ Created model: text-embedding-3-small
# ✅ Created model: claude-3-sonnet-20240229
```

### **Test 2: Check API Endpoints**
```bash
# Test models endpoint
curl http://localhost:8000/api/v1/models

# Should return a list of available models
```

### **Test 3: Test AI Assistant**
1. Open the frontend
2. Go to AI Assistant section
3. Ask a question
4. Should get a proper AI response instead of the error

## 🚨 **Common Issues and Solutions**

### **Issue: "Model is not a LanguageModel: None"**
**Solution**: Run `python init_models.py` to initialize default models

### **Issue: "Failed to initialize default models configuration"**
**Solution**: 
1. Check database connection
2. Ensure SurrealDB is running
3. Check environment variables

### **Issue: "OPENAI_API_KEY not found"**
**Solution**: Add your API keys to the `.env` file

### **Issue: "No module named 'open_notebook'"**
**Solution**: Make sure you're running from the correct directory and all dependencies are installed

## 📋 **Required Environment Variables**

### **Essential (at least one required)**
- `OPENAI_API_KEY` - For OpenAI models (GPT-4, GPT-3.5, embeddings)
- `ANTHROPIC_API_KEY` - For Anthropic models (Claude)
- `GROQ_API_KEY` - For Groq models (Llama, Mixtral)

### **Database**
- `SURREAL_NAMESPACE=fastapi_backend`
- `SURREAL_DATABASE=production`
- `SURREAL_URL=ws://localhost:8000/rpc`

### **Optional**
- `GOOGLE_API_KEY` - For Google models
- `MISTRAL_API_KEY` - For Mistral models
- `DEEPSEEK_API_KEY` - For DeepSeek models

## 🎯 **Expected Behavior After Fix**

### **✅ AI Assistant Should:**
1. **Load properly** without errors
2. **Respond to questions** with AI-generated content
3. **Show proper model status** in the interface
4. **Handle different model types** (chat, embedding, etc.)

### **✅ Error Messages Should:**
1. **Be informative** instead of "Model is not a LanguageModel: None"
2. **Provide helpful guidance** for missing API keys
3. **Show proper model configuration** status

## 🚀 **Quick Fix Commands**

### **If AI Assistant Still Shows Error:**
```bash
# 1. Stop the backend (Ctrl+C)
# 2. Reinitialize models
python init_models.py

# 3. Restart backend
python run.py

# 4. Test in frontend
```

### **If Models Don't Initialize:**
```bash
# Check database connection
python -c "
from src.open_notebook.database.repository import db_connection
with db_connection() as db:
    print('✅ Database connection successful')
"

# Check environment variables
python -c "
import os
print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')
print('ANTHROPIC_API_KEY:', 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'NOT SET')
"
```

## 🎉 **Success Indicators**

You'll know the AI Assistant is working when:
- ✅ No "Model is not a LanguageModel: None" error
- ✅ AI responses are generated properly
- ✅ Model selection works in the interface
- ✅ Different AI providers are available
- ✅ Embeddings and other model types work

## 📞 **Still Having Issues?**

If the AI Assistant still doesn't work:

1. **Check logs**: Look at the backend console for error messages
2. **Verify API keys**: Make sure they're valid and have sufficient credits
3. **Test database**: Ensure SurrealDB is running and accessible
4. **Check network**: Ensure internet connection for API calls
5. **Restart everything**: Stop backend, restart database, restart backend

The AI Assistant should now work properly! 🎉
