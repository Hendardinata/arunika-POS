import express from 'express';
import { prisma } from '../db';
import { authenticateToken, AuthRequest } from '../middleware/auth';

const router = express.Router();

// Get all settings
router.get('/', async (req, res) => {
  try {
    const settings = await prisma.systemSettings.findMany();
    res.json(settings);
  } catch (error) {
    console.error('Failed to fetch settings:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Update or create a setting
router.post('/', async (req, res) => {
  const { key, value, description } = req.body;

  if (!key || !value) {
    res.status(400).json({ error: 'Key and value are required' });
    return;
  }

  try {
    const setting = await prisma.systemSettings.upsert({
      where: { key },
      update: { value, description },
      create: { key, value, description }
    });

    res.json(setting);
  } catch (error) {
    console.error('Failed to update setting:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

export default router;
