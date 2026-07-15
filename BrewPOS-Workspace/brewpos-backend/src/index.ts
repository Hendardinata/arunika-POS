import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import categoryRoutes from './routes/category';
import menuRoutes from './routes/menu';
import authRoutes from './routes/auth';
import settingsRoutes from './routes/settings';
import checkoutRoutes from './routes/checkout';
import customerRoutes from './routes/customer';
import analyticsRoutes from './routes/analytics';
import gamificationRoutes from './routes/gamification';
import inventoryRoutes from './routes/inventory';
import expensesRoutes from './routes/expenses';
import recipeRoutes from './routes/recipe';
import './cron';

dotenv.config();

const app = express();
const port = process.env.PORT || 3001;

import path from 'path';

app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ limit: '10mb', extended: true }));
app.use('/uploads', express.static(path.join(__dirname, '../public/uploads')));

app.use('/api/categories', categoryRoutes);
app.use('/api/menus', menuRoutes);
app.use('/api/auth', authRoutes);
app.use('/api/settings', settingsRoutes);
app.use('/api/checkout', checkoutRoutes);
app.use('/api/customers', customerRoutes);
app.use('/api/analytics', analyticsRoutes);
app.use('/api/gamification', gamificationRoutes);
app.use('/api/inventory', inventoryRoutes);
app.use('/api/expenses', expensesRoutes);
app.use('/api/recipes', recipeRoutes);

app.get('/', (req, res) => {
  res.send('BrewPOS API is running');
});

app.listen(Number(port), '0.0.0.0', () => {
  console.log(`[server]: Server is running at http://127.0.0.1:${port}`);
});
