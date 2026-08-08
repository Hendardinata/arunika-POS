import express from 'express';
import { prisma } from '../db';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const logs = await prisma.systemLog.findMany({
      orderBy: { createdAt: 'desc' },
      take: 200,
      include: {
        user: {
          select: { username: true, role: true }
        }
      }
    });
    res.json(logs);
  } catch (error) {
    console.error('Failed to fetch system logs', error);
    res.status(500).json({ error: 'Failed to fetch system logs' });
  }
});

export default router;
