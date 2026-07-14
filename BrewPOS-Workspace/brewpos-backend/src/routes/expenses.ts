import { Router } from 'express';
import { prisma } from '../db';
import multer from 'multer';
import path from 'path';
import fs from 'fs';

const router = Router();

// Ensure uploads directory exists
const uploadDir = path.join(__dirname, '../../public/uploads/receipts');
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, uniqueSuffix + path.extname(file.originalname));
  }
});
const upload = multer({ storage });

// --- EXPENSE CATEGORIES ---

// Get all expense categories
router.get('/categories', async (req, res) => {
  try {
    const categories = await prisma.expenseCategory.findMany();
    res.json(categories);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch expense categories' });
  }
});

// Create expense category
router.post('/categories', async (req, res) => {
  try {
    const { name, description } = req.body;
    const category = await prisma.expenseCategory.create({
      data: { name, description }
    });
    res.status(201).json(category);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create expense category' });
  }
});

// --- EXPENSES ---

// Get all expenses
router.get('/', async (req, res) => {
  try {
    const { days } = req.query;
    let dateFilter = {};
    
    if (days && days !== 'all') {
      const daysInt = parseInt(days as string);
      if (!isNaN(daysInt)) {
        const targetDate = new Date();
        if (daysInt === 1) {
          targetDate.setHours(0, 0, 0, 0);
        } else {
          targetDate.setDate(targetDate.getDate() - daysInt);
        }
        dateFilter = {
          date: {
            gte: targetDate
          }
        };
      }
    }

    const expenses = await prisma.expense.findMany({
      where: dateFilter,
      include: {
        category: true,
        recordedBy: {
          select: { id: true, username: true, role: true }
        }
      },
      orderBy: { date: 'desc' }
    });
    res.json(expenses);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch expenses' });
  }
});

// Get expense summary (total per month/day etc)
router.get('/summary', async (req, res) => {
  try {
    const expenses = await prisma.expense.findMany();
    const totalExpenses = expenses.reduce((acc, curr) => acc + curr.amount, 0);
    
    // Group by category
    const categoryGroup = await prisma.expense.groupBy({
      by: ['categoryId'],
      _sum: { amount: true }
    });

    res.json({ totalExpenses, categoryGroup });
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch expense summary' });
  }
});

// Create expense
// Assuming user ID is sent in body for simplicity, or we should use auth middleware to get req.user.id
// For now, let's accept userId in body as many other endpoints might do in this simple POS
router.post('/', upload.single('receipt'), async (req, res) => {
  try {
    const { amount, date, notes, categoryId, userId } = req.body;
    let receiptUrl = null;
    
    if (req.file) {
      receiptUrl = `/uploads/receipts/${req.file.filename}`;
    }

    const expense = await prisma.expense.create({
      data: {
        amount: Number(amount),
        date: date ? new Date(date) : new Date(),
        notes,
        categoryId: Number(categoryId),
        userId: Number(userId),
        receiptUrl
      },
      include: {
        category: true,
        recordedBy: { select: { username: true } }
      }
    });
    res.status(201).json(expense);
  } catch (error) {
    console.error('Error creating expense:', error);
    res.status(500).json({ error: 'Failed to create expense', details: error instanceof Error ? error.message : String(error) });
  }
});

// Seed default categories
router.post('/seed-categories', async (req, res) => {
  try {
    const defaultCategories = ['Bahan Baku', 'Operasional', 'Gaji', 'Sewa', 'Lain-lain'];
    const created = [];
    
    for (const name of defaultCategories) {
      const existing = await prisma.expenseCategory.findUnique({ where: { name } });
      if (!existing) {
        const cat = await prisma.expenseCategory.create({ data: { name } });
        created.push(cat);
      }
    }
    
    res.json({ message: 'Seeded default categories', created });
  } catch (error) {
    res.status(500).json({ error: 'Failed to seed categories' });
  }
});

export default router;
