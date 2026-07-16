import express from 'express';
import { prisma } from '../db';
import jwt from 'jsonwebtoken';

const router = express.Router();
const JWT_SECRET = process.env.JWT_SECRET || 'fallback_secret_for_development_only';

// Middleware to authenticate user
const authenticate = (req: any, res: any, next: any) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'Unauthorized' });

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
};

// Open a shift
router.post('/open', authenticate, async (req: any, res: any) => {
  const { startingCash } = req.body;
  const userId = req.user.id;

  try {
    // Check if there's already an open shift
    const existingShift = await prisma.shift.findFirst({
      where: { userId, status: 'OPEN' }
    });

    if (existingShift) {
      return res.status(400).json({ error: 'You already have an open shift', shift: existingShift });
    }

    // Get user to check assigned shift
    const user = await prisma.user.findUnique({ where: { id: userId } });
    if (!user) return res.status(404).json({ error: 'User not found' });
    
    // Default to MORNING if not assigned, or if they are admin opening a shift
    const type = user.assignedShift || 'MORNING';

    const shift = await prisma.shift.create({
      data: {
        userId,
        type,
        status: 'OPEN',
        startingCash: startingCash || 0,
        startTime: new Date()
      }
    });

    res.status(201).json(shift);
  } catch (error) {
    console.error('Error opening shift:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Get current shift
router.get('/current', authenticate, async (req: any, res: any) => {
  const userId = req.user.id;

  try {
    const shift = await prisma.shift.findFirst({
      where: { userId, status: 'OPEN' }
    });

    if (!shift) {
      return res.json({ currentShift: null });
    }

    res.json({ currentShift: shift });
  } catch (error) {
    console.error('Error getting current shift:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Close shift
router.post('/close', authenticate, async (req: any, res: any) => {
  const { endingCash } = req.body;
  const userId = req.user.id;

  try {
    const shift = await prisma.shift.findFirst({
      where: { userId, status: 'OPEN' }
    });

    if (!shift) {
      return res.status(404).json({ error: 'No open shift found' });
    }

    // Calculate expected cash from transactions
    const transactions = await prisma.transaction.findMany({
      where: { shiftId: shift.id }
    });
    
    // Expected = startingCash + total from cash transactions
    let cashIncome = 0;
    for (const t of transactions) {
      if (t.paymentMethod === 'CASH') {
        cashIncome += t.totalAmount;
      }
    }
    
    const expectedEndingCash = shift.startingCash + cashIncome;

    const closedShift = await prisma.shift.update({
      where: { id: shift.id },
      data: {
        status: 'CLOSED',
        endTime: new Date(),
        endingCash: endingCash || 0,
        expectedEndingCash
      }
    });

    res.json(closedShift);
  } catch (error) {
    console.error('Error closing shift:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Get shift reports
router.get('/reports', async (req: any, res: any) => {
  try {
    const shifts = await prisma.shift.findMany({
      include: {
        user: {
          select: { username: true }
        },
        transactions: true
      },
      orderBy: { createdAt: 'desc' },
      take: 50 // Limit for now
    });

    res.json(shifts);
  } catch (error) {
    console.error('Error fetching shift reports:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

export default router;
