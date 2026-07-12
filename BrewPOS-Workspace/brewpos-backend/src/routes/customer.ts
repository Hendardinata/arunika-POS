import { Router } from 'express';
import { prisma } from '../db';

const router = Router();

router.get('/', async (req, res) => {
  try {
    const customers = await prisma.customer.findMany({
      orderBy: { points: 'desc' },
      include: {
        _count: {
          select: { transactions: true },
        },
        badges: {
          include: { badge: true }
        },
        quests: {
          include: { quest: true }
        }
      },
    });
    res.json(customers);
  } catch (error) {
    console.error('Error fetching customers:', error);
    res.status(500).json({ error: 'Failed to fetch customers', details: error instanceof Error ? error.message : String(error) });
  }
});

router.get('/search', async (req, res) => {
  try {
    const { nickname } = req.query;
    if (!nickname || typeof nickname !== 'string') {
      return res.status(400).json({ error: 'Nickname query parameter is required' });
    }

    const customer = await prisma.customer.findUnique({
      where: { nickname: nickname },
      include: {
        badges: {
          include: { badge: true }
        },
        quests: {
          include: { quest: true }
        }
      }
    });

    if (!customer) {
      return res.status(404).json({ error: 'Customer not found' });
    }

    res.json(customer);
  } catch (error) {
    console.error('Error fetching customer by nickname:', error);
    res.status(500).json({ error: 'Failed to fetch customer' });
  }
});

export default router;
